"""엔진 A 추출 정확도와 서류 분류 정확도를 평가한다.

정답 라벨이 빠진 칸(글씨는 있는데 라벨 없음, scripts.build_ink 참고)은 정답을 모르므로 채점에서 뺀다.

실행:
  .venv/Scripts/python -m scripts.run_eval extract   # 청구서 400장 (약 5분) → 예측 저장 후 채점
  .venv/Scripts/python -m scripts.run_eval score     # 저장된 예측으로 채점만 다시
  .venv/Scripts/python -m scripts.run_eval classify  # 검증 서류 1,598장
  .venv/Scripts/python -m scripts.run_eval compare   # 엔진 B가 처리한 100장에서 엔진 A·B 비교
"""
import csv
import json
import sys
import time
from collections import Counter

from src.classify import classify, load_classifier
from src.extract_paddle import extract_fields, load_recognizer
from src.load_data import PROJECT_ROOT, list_documents, load_image
from src.metrics import cer, is_exact
from scripts.build_ink import load_ink, unlabeled_fields

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
PRED_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
RESULTS = PROJECT_ROOT / "results"
# 이 확신도 이상인 칸만 자동 처리 후보로 본다 (설계서 4.8 기본값)
HIGH_CONFIDENCE = 0.85


def load_ground_truth(split, form_code):
    rows = {}
    with open(GT_DIR / f"{split}_{form_code}.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            rows[row["doc_id"]] = row["fields"]
    return rows


def run_extract():
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    recognizer = load_recognizer()
    for form_code in ["15", "16"]:
        docs = [d for d in list_documents("val", ["2-5.청구서"]) if d["form_code"] == form_code]
        with open(PRED_DIR / f"paddle_val_{form_code}.jsonl", "w", encoding="utf-8") as out:
            for doc in docs:
                image = load_image(doc)
                start = time.perf_counter()
                extracted = extract_fields(image, form_code, recognizer)
                seconds = time.perf_counter() - start
                out.write(json.dumps({"doc_id": doc["doc_id"], "form_code": form_code, "engine": "paddle",
                                      "seconds": round(seconds, 3), "fields": extracted}, ensure_ascii=False) + "\n")
    run_score()


def score_fields(fields, truth, unlabeled, per_field):
    """칸별 (완전 일치, 글자 오류율, 확신도)를 모은다. 정답 라벨이 빠진 칸은 건너뛰고 그 수를 돌려준다."""
    skipped = 0
    for name, result in fields.items():
        if name in unlabeled:
            skipped += 1
            continue
        expected = truth.get(name, "")
        per_field.setdefault(name, []).append(
            (is_exact(result["value"], expected, name), cer(result["value"], expected, name), result["score"]))
    return skipped


def run_score():
    """저장된 엔진 A 예측을 채점한다 (OCR을 다시 돌리지 않음)."""
    field_rows = []
    summary_rows = []
    for form_code in ["15", "16"]:
        truth_by_doc = load_ground_truth("val", form_code)
        ink_by_doc = load_ink(form_code)
        docs = _read_predictions("paddle", form_code)
        per_field, skipped = {}, 0
        total_seconds = sum(row["seconds"] for row in docs.values())
        for doc_id, row in docs.items():
            truth = truth_by_doc[doc_id]
            skipped += score_fields(row["fields"], truth, unlabeled_fields(truth, ink_by_doc[doc_id]), per_field)

        all_results = [r for results in per_field.values() for r in results]
        high = [r for r in all_results if r[2] >= HIGH_CONFIDENCE]
        for name, results in per_field.items():
            field_rows.append({
                "form_code": form_code,
                "field": name,
                "documents": len(results),
                "exact_rate": round(sum(r[0] for r in results) / len(results), 3),
                "mean_cer": round(sum(r[1] for r in results) / len(results), 3),
            })
        summary_rows.append({
            "engine": "paddle",
            "form_code": form_code,
            "documents": len(docs),
            "field_exact_rate": round(sum(r[0] for r in all_results) / len(all_results), 3),
            "mean_cer": round(sum(r[1] for r in all_results) / len(all_results), 3),
            "unlabeled_skipped": skipped,
            "sec_per_doc": round(total_seconds / len(docs), 2),
            "high_conf_share": round(len(high) / len(all_results), 3),
            "high_conf_exact_rate": round(sum(r[0] for r in high) / len(high), 3) if high else 0.0,
        })
        print(summary_rows[-1])

    _write_csv(RESULTS / "eval_engine_a_fields.csv", field_rows)
    _write_csv(RESULTS / "eval_summary.csv", summary_rows)


def run_classify():
    centroids, max_distance = load_classifier()
    confusion = Counter()
    docs = list_documents("val")
    for doc in docs:
        predicted, _ = classify(load_image(doc), centroids, max_distance)
        confusion[(doc["form_code"], predicted)] += 1
    correct = sum(count for (truth, pred), count in confusion.items() if truth == pred)
    rows = [{"truth": t, "predicted": p, "count": c} for (t, p), c in sorted(confusion.items())]
    _write_csv(RESULTS / "eval_classify.csv", rows)
    print(f"분류 정확도 {correct}/{len(docs)} = {correct / len(docs):.4f}")
    for row in rows:
        if row["truth"] != row["predicted"]:
            print("오분류:", row)


def _read_predictions(engine, form_code):
    with open(PRED_DIR / f"{engine}_val_{form_code}.jsonl", encoding="utf-8") as f:
        return {row["doc_id"]: row for row in map(json.loads, f)}


def run_compare():
    """엔진 B가 처리한 서류만 골라 두 엔진을 같은 조건에서 비교한다."""
    summary_rows, field_rows = [], []
    for form_code in ["15", "16"]:
        truth_by_doc = load_ground_truth("val", form_code)
        ink_by_doc = load_ink(form_code)
        claude = _read_predictions("claude", form_code)
        paddle = _read_predictions("paddle", form_code)
        doc_ids = sorted(claude)
        for engine, predictions in [("paddle", paddle), ("claude", claude)]:
            per_field, seconds, skipped = {}, [], 0
            for doc_id in doc_ids:
                row = predictions[doc_id]
                seconds.append(row["seconds"])
                truth = truth_by_doc[doc_id]
                skipped += score_fields(row["fields"], truth, unlabeled_fields(truth, ink_by_doc[doc_id]), per_field)
            results = [r for rs in per_field.values() for r in rs]
            low = [r for r in results if r[2] < HIGH_CONFIDENCE]
            high = [r for r in results if r[2] >= HIGH_CONFIDENCE]
            summary_rows.append({
                "engine": engine,
                "form_code": form_code,
                "documents": len(doc_ids),
                "field_exact_rate": round(sum(r[0] for r in results) / len(results), 3),
                "mean_cer": round(sum(r[1] for r in results) / len(results), 3),
                "unlabeled_skipped": skipped,
                "sec_per_doc": round(sum(seconds) / len(seconds), 2),
                "low_conf_share": round(len(low) / len(results), 3),
                "low_conf_exact_rate": round(sum(r[0] for r in low) / len(low), 3) if low else "",
                "high_conf_exact_rate": round(sum(r[0] for r in high) / len(high), 3) if high else "",
            })
            print(summary_rows[-1])
            for name, rs in per_field.items():
                field_rows.append({"engine": engine, "form_code": form_code, "field": name,
                                   "exact_rate": round(sum(r[0] for r in rs) / len(rs), 3)})
    _write_csv(RESULTS / "eval_engine_compare.csv", summary_rows)
    _write_csv(RESULTS / "eval_engine_compare_fields.csv", field_rows)


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    {"extract": run_extract, "score": run_score, "classify": run_classify, "compare": run_compare}[sys.argv[1]]()
