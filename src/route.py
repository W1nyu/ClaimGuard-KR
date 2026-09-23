"""처리 결정: 자동접수 / 보완요청 / 담당자검토.

우선순위
1. 담당자검토: 사람이 판단할 규칙 위반, 확인불가, 또는 값이 있는데 확신도가 낮은 칸
2. 보완요청: 고객이 고치거나 서류를 더 내야 하는 위반
3. 자동접수: 모두 통과
결정마다 사유를 함께 돌려줘서 왜 그렇게 판단했는지 설명할 수 있게 한다.
"""
from src.validate import DOCUMENT, REVIEW, SUPPLEMENT

AUTO = "자동접수"
SUPPLEMENT_DECISION = "보완요청"
REVIEW_DECISION = "담당자검토"
CONFIDENCE_THRESHOLD = 0.85


def customer_message(results):
    """고객에게 보낼 보완 안내문. LLM 없이 규칙 문장을 번호 목록으로 엮는다."""
    lines = ["고객님, 보험금 청구서류 접수 중 아래 사항의 확인이 필요합니다."]
    for number, result in enumerate(results, start=1):
        lines.append(f"{number}. {result['message']}")
    lines.append("내용을 확인하신 뒤 수정한 서류를 모바일 앱 또는 고객센터를 통해 다시 제출해 주세요.")
    return "\n".join(lines)


def decide(rule_results, extracted=None, threshold=CONFIDENCE_THRESHOLD):
    failed = [r for r in rule_results if r["status"] != "pass"]
    review = [r for r in failed if r["action"] == REVIEW]
    for_customer = [r for r in failed if r["action"] in (SUPPLEMENT, DOCUMENT)]
    low = sorted(
        name for name, field in (extracted or {}).items()
        if field["value"] and field["score"] < threshold
    )

    reasons = [f"[{r['rule']}] {r['message']}" for r in failed]
    reasons += [f"[확신도] '{name}' 칸 확신도 {extracted[name]['score']:.2f} < {threshold}" for name in low]

    if review or low:
        decision = REVIEW_DECISION
    elif for_customer:
        decision = SUPPLEMENT_DECISION
    else:
        decision = AUTO
    return {
        "decision": decision,
        "reasons": reasons,
        "customer_message": customer_message(for_customer) if for_customer else None,
        "low_confidence_fields": low,
    }
