"""엔진 B 일괄 추출: 양식 15·16 검증 데이터에서 앞 50장씩 (총 100장).

응답 원문을 서류마다 저장하므로 중간에 멈춰도 다시 실행하면 이어서 한다.
실행: .venv/Scripts/python -m scripts.run_claude_batch
"""
import json
import time

from src.extract_claude import extract_fields_cli, parse_response
from src.load_data import PROJECT_ROOT, list_documents, load_image

OUT_DIR = PROJECT_ROOT / "data" / "processed" / "claude_outputs"
PRED_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
PER_FORM = 50


def sample_documents(form_code):
    docs = [d for d in list_documents("val", ["2-5.청구서"]) if d["form_code"] == form_code]
    return sorted(docs, key=lambda d: d["doc_id"])[:PER_FORM]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    for form_code in ["15", "16"]:
        rows = []
        for number, doc in enumerate(sample_documents(form_code), start=1):
            text_path = OUT_DIR / f"{doc['doc_id']}.txt"
            meta_path = OUT_DIR / f"{doc['doc_id']}.json"
            if not text_path.exists():
                captured = {}

                def recording_runner(prompt):
                    # 실제 CLI를 부르고 응답 원문을 남긴다
                    from src.extract_claude import _run_claude
                    captured["text"] = _run_claude(prompt, timeout=180)
                    return captured["text"]

                start = time.perf_counter()
                try:
                    extract_fields_cli(load_image(doc), form_code, runner=recording_runner)
                except Exception as error:  # 한 장 실패해도 나머지는 계속
                    print(f"[{form_code} {number}/{PER_FORM}] {doc['doc_id']} 실패: {error}")
                    continue
                seconds = time.perf_counter() - start
                text_path.write_text(captured["text"], encoding="utf-8")
                meta_path.write_text(json.dumps({"seconds": round(seconds, 1)}), encoding="utf-8")
                print(f"[{form_code} {number}/{PER_FORM}] {doc['doc_id']} {seconds:.1f}초", flush=True)
            fields = parse_response(text_path.read_text(encoding="utf-8"), form_code)
            seconds = json.loads(meta_path.read_text(encoding="utf-8"))["seconds"]
            rows.append({"doc_id": doc["doc_id"], "form_code": form_code, "engine": "claude",
                         "seconds": seconds, "fields": fields})
        with open(PRED_DIR / f"claude_val_{form_code}.jsonl", "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"양식 {form_code}: {len(rows)}장 저장")


if __name__ == "__main__":
    main()
