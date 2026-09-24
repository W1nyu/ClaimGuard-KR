"""OCR 오류가 처리 결정을 얼마나 바꾸는지 측정한다 (결정 일치율).

같은 서류에 대해
  - 정답 값으로 검증·결정한 결과 (기준)
  - 엔진 값으로 규칙만 적용한 결과
  - 엔진 값 + 칸 확신도까지 적용한 결과 (실제 운영 방식)
를 비교한다. 가장 위험한 경우는 '잘못된 자동접수': 정답은 자동접수가 아닌데 시스템이 자동접수한 건.
고객 쪽에서 가장 나쁜 경우는 '거짓 보완 요청': 정답으로는 통과인 규칙이 고객 보완요청 항목으로 들어간 서류.

엔진 값은 두 가지로 본다.
  - 잉크 판단 없음: OCR 값 그대로 (빈 글자는 빈칸)
  - 잉크 판단: 칸에 글씨가 있는데 비었으면 '읽지 못함'(R12 담당자 확인), 글씨가 없으면 값을 비움

정답 라벨이 빠진 칸(scripts.build_ink)은 정답을 모른다.
  - R01은 '비어 있지 않음'만 알면 되므로 그 칸을 채워진 것으로 보고 비교한다.
  - 다른 규칙은 그 칸을 읽는 경우 비교에서 뺀다.
  - 서류 단위 결정은 라벨이 빠진 칸이 없는 서류에서만 비교한다.

실행:
  .venv/Scripts/python -m scripts.run_decision_eval          # 엔진 A, 청구서 400장
  .venv/Scripts/python -m scripts.run_decision_eval compare  # 엔진 B가 처리한 100장에서 엔진 A·B
"""
import sys
import csv
import json
from collections import Counter
from datetime import date

from scripts.build_ink import load_ink, unlabeled_fields
from src.ink import apply_ink, unread_fields
from src.load_data import PROJECT_ROOT
from src.route import AUTO, decide
from src.validate import ADDRESS_FIELDS, DOCUMENT, SUPPLEMENT, validate

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
PRED_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
RESULTS = PROJECT_ROOT / "results"
# 재현할 수 있도록 평가 기준일을 고정한다
EVAL_DATE = date(2026, 9, 23)
RULES = [f"R{n:02d}" for n in range(1, 12)]
VARIANTS = ["잉크 판단 없음", "잉크 판단"]

DATE_FIELDS = {
    "16": ["사고_년", "사고_월", "사고_일", "작성_년", "작성_월", "작성_일"],
    "15": ["사고일자", "청구_년", "청구_월", "청구_일"],
}


def rule_inputs(form_code):
    """규칙마다 읽는 칸. 정답 라벨이 빠진 칸을 읽는 규칙은 정답 결과를 알 수 없다."""
    dates = DATE_FIELDS[form_code]
    return {
        "R02": dates, "R03": dates, "R04": dates, "R05": ["주민번호"], "R06": ["연락처", "이메일"],
        "R07": ADDRESS_FIELDS, "R08": ["진단명"], "R09": ["직업"], "R10": ["은행명", "계좌번호"],
        "R11": ["예금주", "피보험자_성명"],
    }


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def statuses(results):
    return {r["rule"]: r["status"] for r in results}


def predicted(form_code, fields, ink, variant):
    """엔진 결과로 검증·결정한다. variant에 따라 잉크 판단을 적용한다."""
    if variant == "잉크 판단":
        fields = apply_ink(fields, ink)
    values = {name: field["value"] for name, field in fields.items()}
    unread = unread_fields(fields) if variant == "잉크 판단" else []
    rules = validate(form_code, values, today=EVAL_DATE, unread=unread)
    return rules, decide(rules)["decision"], decide(rules, extracted=fields)["decision"]


def evaluate(form_code, engine="paddle", doc_ids=None):
    truth_by_doc = {r["doc_id"]: r["fields"] for r in read_jsonl(GT_DIR / f"val_{form_code}.jsonl")}
    ink_by_doc = load_ink(form_code)
    predictions = read_jsonl(PRED_DIR / f"{engine}_val_{form_code}.jsonl")
    if doc_ids is not None:
        predictions = [p for p in predictions if p["doc_id"] in doc_ids]
    inputs = rule_inputs(form_code)

    summaries, rule_rows = [], []
    for variant in VARIANTS:
        truth_decisions, rule_only, with_conf = Counter(), Counter(), Counter()
        agree_rule_only = agree_with_conf = false_auto = complete = 0
        false_customer = false_r01 = held_for_unread = 0
        false_customer_rules = Counter()
        rule_agree, rule_seen, truth_fail, rule_held = Counter(), Counter(), Counter(), Counter()

        for pred in predictions:
            truth = truth_by_doc[pred["doc_id"]]
            unlabeled = unlabeled_fields(truth, ink_by_doc[pred["doc_id"]])
            # 라벨이 빠진 칸은 글씨가 있으므로 R01에서는 채워진 칸으로 본다
            truth_rules = validate(form_code, truth, today=EVAL_DATE, unread=unlabeled)
            pred_rules, rules_decision, conf_decision = predicted(
                form_code, pred["fields"], ink_by_doc[pred["doc_id"]], variant)
            truth_status, pred_status = statuses(truth_rules), statuses(pred_rules)
            held = {r["rule"] for r in pred_rules if r["detail"].get("held_for_unread")}

            comparable = [rule for rule in RULES
                          if rule == "R01" or not set(inputs.get(rule, [])) & unlabeled]
            for rule in comparable:
                if rule in truth_status or rule in pred_status:
                    rule_seen[rule] += 1
                    rule_held[rule] += rule in held
                    rule_agree[rule] += truth_status.get(rule, "n/a") == pred_status.get(rule, "n/a")
                    truth_fail[rule] += truth_status.get(rule) in ("fail", "unknown")

            # 고객에게 가는 항목 중 정답으로는 통과인 것
            wrong_for_customer = [r["rule"] for r in pred_rules
                                  if r["status"] == "fail" and r["action"] in (SUPPLEMENT, DOCUMENT)
                                  and r["rule"] in comparable and truth_status.get(r["rule"], "pass") == "pass"]
            false_customer += bool(wrong_for_customer)
            false_customer_rules.update(wrong_for_customer)
            false_r01 += "R01" in wrong_for_customer
            held_for_unread += "R12" in pred_status

            if not unlabeled:
                complete += 1
                truth_decision = decide(truth_rules)["decision"]
                truth_decisions[truth_decision] += 1
                rule_only[rules_decision] += 1
                with_conf[conf_decision] += 1
                agree_rule_only += truth_decision == rules_decision
                agree_with_conf += truth_decision == conf_decision
                false_auto += conf_decision == AUTO and truth_decision != AUTO

        summaries.append({
            "engine": engine,
            "form_code": form_code,
            "variant": variant,
            "documents": len(predictions),
            "false_customer_docs": false_customer,
            "false_r01_docs": false_r01,
            "false_customer_rules": dict(false_customer_rules),
            "held_for_unread_docs": held_for_unread,
            "complete_documents": complete,
            "truth_decisions": dict(truth_decisions),
            "rule_only_decisions": dict(rule_only),
            "rule_only_agreement": round(agree_rule_only / complete, 3) if complete else "",
            "with_conf_decisions": dict(with_conf),
            "with_conf_agreement": round(agree_with_conf / complete, 3) if complete else "",
            "false_auto": false_auto,
        })
        rule_rows += [{
            "engine": engine,
            "form_code": form_code,
            "variant": variant,
            "rule": rule,
            "documents": rule_seen[rule],
            "truth_violation_rate": round(truth_fail[rule] / rule_seen[rule], 3),
            "status_agreement": round(rule_agree[rule] / rule_seen[rule], 3),
            # 읽지 못한 칸 때문에 담당자 판단으로 보류한 비율, 보류하지 않은 서류에서의 일치율
            "held_for_reviewer": round(rule_held[rule] / rule_seen[rule], 3),
            "decided_agreement": round(rule_agree[rule] / (rule_seen[rule] - rule_held[rule]), 3)
            if rule_seen[rule] > rule_held[rule] else "",
        } for rule in RULES if rule_seen[rule]]
    return summaries, rule_rows


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
            engine_summaries, rule_rows = evaluate(form_code, engine, ids)
            summaries += engine_summaries
            all_rule_rows += rule_rows
            for summary in engine_summaries:
                print(summary)
            for row in rule_rows:
                print("  ", row)
    suffix = "_claude" if mode == "compare" else ""
    write_csv(RESULTS / f"eval_decisions{suffix}.csv", summaries)
    write_csv(RESULTS / f"eval_rules{suffix}.csv", all_rule_rows)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "paddle")
