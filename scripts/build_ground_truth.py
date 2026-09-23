"""라벨 박스를 칸에 배정해 청구서·위임장 항목별 정답 파일을 만든다.

실행: .venv/Scripts/python -m scripts.build_ground_truth
"""
import csv
import json

from src.form_templates import assign_boxes_to_fields, load_form_fields
from src.load_data import CATEGORY_BY_FORM, PROJECT_ROOT, label_boxes, list_documents, load_label

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
REPORT_PATH = PROJECT_ROOT / "results" / "ground_truth_report.csv"


def build(split, form_code):
    fields = load_form_fields(form_code)
    docs = [d for d in list_documents(split, [CATEGORY_BY_FORM[form_code]]) if d["form_code"] == form_code]
    total_boxes = 0
    unassigned_boxes = 0
    filled = {name: 0 for name in fields}
    out_path = GT_DIR / f"{split}_{form_code}.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for doc in docs:
            boxes = label_boxes(load_label(doc))
            values, unassigned = assign_boxes_to_fields(boxes, fields)
            total_boxes += len(boxes)
            unassigned_boxes += len(unassigned)
            for name in values:
                filled[name] += 1
            row = {"doc_id": doc["doc_id"], "form_code": form_code, "split": split, "fields": values}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "split": split,
        "form_code": form_code,
        "documents": len(docs),
        "boxes": total_boxes,
        "unassigned_boxes": unassigned_boxes,
        "unassigned_rate": round(unassigned_boxes / total_boxes, 4),
        "fill_rate": filled,
    }


def main():
    GT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for split in ["train", "val"]:
        for form_code in ["12", "15", "16"]:
            summary = build(split, form_code)
            print(f"{split} {form_code}: 서류 {summary['documents']}장, 배정 실패 {summary['unassigned_rate']:.2%}")
            for name, count in summary["fill_rate"].items():
                rows.append({
                    "split": split,
                    "form_code": form_code,
                    "field": name,
                    "fill_rate": round(count / summary["documents"], 3),
                    "unassigned_rate": summary["unassigned_rate"],
                })
    with open(REPORT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "form_code", "field", "fill_rate", "unassigned_rate"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"보고서 저장: {REPORT_PATH}")


if __name__ == "__main__":
    main()
