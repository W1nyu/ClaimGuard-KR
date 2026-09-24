"""검증 서류의 칸별 잉크 비율을 저장하고, 정답 라벨이 빠진 칸을 찾는다.

AI Hub 라벨에는 손글씨가 있는데도 박스가 없는 칸이 있다(예: 예금주 칸에 '교라현'이 적혀 있지만 라벨 없음).
이런 칸을 '빈칸 정답'으로 채점하면 엔진이 제대로 읽어도 오답이 된다.
칸에 잉크가 있는데 라벨이 없으면 '정답 없음(unlabeled)'으로 보고 평가에서 뺀다.

결과
  data/processed/ink/val_{양식}.jsonl        서류별 {칸: 잉크 비율}
  results/ground_truth_unlabeled.csv         양식·칸별 라벨 누락 수

실행: .venv/Scripts/python -m scripts.build_ink
"""
import csv
import json
from collections import Counter

from src.form_templates import load_form_fields
from src.ink import INK_THRESHOLD, field_ink
from src.load_data import CATEGORY_BY_FORM, PROJECT_ROOT, list_documents, load_image

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
INK_DIR = PROJECT_ROOT / "data" / "processed" / "ink"
REPORT_PATH = PROJECT_ROOT / "results" / "ground_truth_unlabeled.csv"
FORMS = ["12", "15", "16"]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_ink(form_code, split="val"):
    """{doc_id: {칸: 잉크 비율}}"""
    return {r["doc_id"]: r["ink"] for r in read_jsonl(INK_DIR / f"{split}_{form_code}.jsonl")}


def unlabeled_fields(truth, ink):
    """글씨는 있는데 정답 라벨이 없는 칸 = 정답을 모르는 칸."""
    return {name for name, ratio in ink.items() if ratio >= INK_THRESHOLD and not truth.get(name)}


def main():
    INK_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for form_code in FORMS:
        truth_by_doc = {r["doc_id"]: r["fields"] for r in read_jsonl(GT_DIR / f"val_{form_code}.jsonl")}
        docs = [d for d in list_documents("val", [CATEGORY_BY_FORM[form_code]]) if d["form_code"] == form_code]
        counts, unlabeled_docs = Counter(), 0
        with open(INK_DIR / f"val_{form_code}.jsonl", "w", encoding="utf-8") as out:
            for doc in docs:
                ink = field_ink(load_image(doc), form_code)
                out.write(json.dumps({"doc_id": doc["doc_id"], "ink": ink}, ensure_ascii=False) + "\n")
                truth = truth_by_doc[doc["doc_id"]]
                unlabeled_docs += bool(unlabeled_fields(truth, ink))
                for name, ratio in ink.items():
                    has_ink, labeled = ratio >= INK_THRESHOLD, bool(truth.get(name))
                    counts[name, "unlabeled" if has_ink and not labeled else
                           "blank" if not labeled else "labeled" if has_ink else "labeled_no_ink"] += 1
        for name in load_form_fields(form_code):
            rows.append({"form_code": form_code, "field": name, "documents": len(docs),
                         "labeled": counts[name, "labeled"], "unlabeled": counts[name, "unlabeled"],
                         "blank": counts[name, "blank"], "labeled_no_ink": counts[name, "labeled_no_ink"]})
        total = {k: sum(r[k] for r in rows if r["form_code"] == form_code)
                 for k in ["labeled", "unlabeled", "blank", "labeled_no_ink"]}
        print(f"{form_code}: 서류 {len(docs)}장 중 라벨 빠진 칸이 있는 서류 {unlabeled_docs}장, {total}")
    with open(REPORT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"보고서 저장: {REPORT_PATH}")


if __name__ == "__main__":
    main()
