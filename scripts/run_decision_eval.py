"""OCR 오류가 처리 결정을 얼마나 바꾸는지 측정한다 (결정 일치율).

같은 서류에 대해
  - 정답 값으로 검증·결정한 결과 (기준)
  - 엔진 A 값으로 규칙만 적용한 결과
  - 엔진 A 값 + 칸 확신도까지 적용한 결과 (실제 운영 방식)
를 비교한다. 가장 위험한 경우는 '잘못된 자동접수': 정답은 자동접수가 아닌데 시스템이 자동접수한 건.

실행:
  .venv/Scripts/python -m scripts.run_decision_eval          # 엔진 A, 청구서 400장
  .venv/Scripts/python -m scripts.run_decision_eval compare  # 엔진 B가 처리한 100장에서 엔진 A·B
"""
import sys
import csv
import json
from collections import Counter
from datetime import date

from src.load_data import PROJECT_ROOT
from src.route import AUTO, decide
from src.validate import validate

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
PRED_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
RESULTS = PROJECT_ROOT / "results"
# 재현할 수 있도록 평가 기준일을 고정한다
EVAL_DATE = date(2026, 9, 23)
RULES = [f"R{n:02d}" for n in range(1, 12)]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def statuses(results):
    return {r["rule"]: r["status"] for r in results}


def evaluate(form_code, engine="paddle", doc_ids=None):
    truth_by_doc = {r["doc_id"]: r["fields"] for r in read_jsonl(GT_DIR / f"val_{form_code}.jsonl")}
    predictions = read_jsonl(PRED_DIR / f"{engine}_val_{form_code}.jsonl")
    if doc_ids is not None:
        predictions = [p for p in predictions if p["doc_id"] in doc_ids]

    truth_decisions, rule_only, with_conf = Counter(), Counter(), Counter()
    agree_rule_only = agree_with_conf = false_auto = 0
    rule_agree, rule_seen, truth_fail = Counter(), Counter(), Counter()

    for pred in predictions:
        truth_rules = validate(form_code, truth_by_doc[pred["doc_id"]], today=EVAL_DATE)
        pred_values = {name: field["value"] for name, field in pred["fields"].items()}
        pred_rules = validate(form_code, pred_values, today=EVAL_DATE)

        truth_decision = decide(truth_rules)["decision"]
        rules_decision = decide(pred_rules)["decision"]
        conf_decision = decide(pred_rules, extracted=pred["fields"])["decision"]

        truth_decisions[truth_decision] += 1
        rule_only[rules_decision] += 1
        with_conf[conf_decision] += 1
        agree_rule_only += truth_decision == rules_decision
        agree_with_conf += truth_decision == conf_decision
        false_auto += conf_decision == AUTO and truth_decision != AUTO

        truth_status, pred_status = statuses(truth_rules), statuses(pred_rules)
        for rule in RULES:
            if rule in truth_status or rule in pred_status:
                rule_seen[rule] += 1
                rule_agree[rule] += truth_status.get(rule, "n/a") == pred_status.get(rule, "n/a")
                truth_fail[rule] += truth_status.get(rule) in ("fail", "unknown")

    total = len(predictions)
    summary = {
        "engine": engine,
        "form_code": form_code,
        "documents": total,
        "truth_decisions": dict(truth_decisions),
        "rule_only_decisions": dict(rule_only),
        "rule_only_agreement": round(agree_rule_only / total, 3),
        "with_conf_decisions": dict(with_conf),
        "with_conf_agreement": round(agree_with_conf / total, 3),
        "false_auto": false_auto,
    }
    rule_rows = [{
        "engine": engine,
        "form_code": form_code,
        "rule": rule,
        "documents": rule_seen[rule],
        "truth_violation_rate": round(truth_fail[rule] / rule_seen[rule], 3),
        "status_agreement": round(rule_agree[rule] / rule_seen[rule], 3),
    } for rule in RULES if rule_seen[rule]]
    return summary, rule_rows


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v for k, v in row.items()})


def main(mode="paddle"):
    summaries, all_rule_rows = [], []
    for form_code in ["15", "16"]:
        if mode == "compare":
            doc_ids = {p["doc_id"] for p in read_jsonl(PRED_DIR / f"claude_val_{form_code}.jsonl")}
            runs = [("paddle", doc_ids), ("claude", doc_ids)]
        else:
            runs = [("paddle", None)]
        for engine, ids in runs:
            summary, rule_rows = evaluate(form_code, engine, ids)
            summaries.append(summary)
            all_rule_rows.extend(rule_rows)
            print(summary)
            for row in rule_rows:
                print("  ", row)
    suffix = "_claude" if mode == "compare" else ""
    write_csv(RESULTS / f"eval_decisions{suffix}.csv", summaries)
    write_csv(RESULTS / f"eval_rules{suffix}.csv", all_rule_rows)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "paddle")
