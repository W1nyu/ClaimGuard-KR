"""서류 1건 처리: 분류 → 추출 → 검증 → 결정 → 기록. 담당자 수정·승인도 여기서 처리한다.

화면(Streamlit)은 이 모듈만 부르면 된다. 추출기·분류기·기준 데이터 조회는 인자로 바꿔 끼울 수 있어
테스트에서는 가짜를 넣는다.
"""
import uuid

from src.audit import get_case, log_decision, log_edit, save_case
from src.load_data import FORM_NAMES
from src.route import REVIEW_DECISION, decide
from src.validate import validate

CLAIM_FORMS = ("15", "16")
ENGINE_NAMES = {"paddle": "엔진 A (PaddleOCR, 로컬)", "claude": "엔진 B (Claude CLI, 외부 모델)"}


def _default_extractors():
    from src.extract_claude import extract_fields_cli
    from src.extract_paddle import extract_fields
    return {"paddle": extract_fields, "claude": extract_fields_cli}


def _default_classifier(image):
    from src.classify import classify, load_classifier
    centroids, max_distance = load_classifier()
    return classify(image, centroids, max_distance)


def _status(decision):
    return "검토대기" if decision == REVIEW_DECISION else "처리완료"


def _evaluate(case, today, refs):
    """현재 값으로 검증·결정을 다시 계산해 case에 채운다."""
    case["rules"] = validate(case["form_code"], case["values"], today=today, refs=refs)
    result = decide(case["rules"], extracted=case["extracted"])
    case.update(result)
    case["status"] = _status(result["decision"])
    return case


def process_document(image, engine="paddle", case_id=None, conn=None, extractors=None, classifier=None,
                     today=None, refs=None):
    extractors = extractors or _default_extractors()
    form_code, _ = (classifier or _default_classifier)(image)
    case = {"case_id": case_id or uuid.uuid4().hex[:12], "form_code": form_code, "engine": engine,
            "engine_note": "", "extracted": {}, "values": {}, "rules": []}

    if form_code not in CLAIM_FORMS:
        name = FORM_NAMES.get(form_code, "알 수 없는 서류")
        case.update({
            "decision": REVIEW_DECISION,
            "reasons": [f"[분류] '{name}'은(는) 항목 자동 추출 대상(보험금 청구서)이 아니어서 담당자가 확인합니다"],
            "customer_message": None, "low_confidence_fields": [], "status": "검토대기",
        })
    else:
        try:
            case["extracted"] = extractors[engine](image, form_code)
        except Exception as error:
            # 엔진 B(외부 모델)가 실패하면 로컬 엔진 A로 대신 처리하고 그 사실을 남긴다
            if engine == "paddle":
                raise
            case["engine"] = "paddle"
            case["engine_note"] = f"엔진 B 실패로 엔진 A 사용: {error}"
            case["extracted"] = extractors["paddle"](image, form_code)
        case["values"] = {name: field["value"] for name, field in case["extracted"].items()}
        _evaluate(case, today, refs)

    if conn is not None:
        save_case(conn, case)
        log_decision(conn, case["case_id"], "AI", case["engine"], case["decision"], case["reasons"])
    return case


def apply_edits(conn, case_id, new_values, editor, today=None, refs=None):
    """담당자가 고친 값을 반영하고 다시 검증한다. 담당자가 확인한 칸은 확신도 1.0."""
    case = get_case(conn, case_id)
    for field, new in new_values.items():
        old = case["values"].get(field, "")
        if new != old:
            log_edit(conn, case_id, field, old, new, editor)
        case["values"][field] = new
        case["extracted"][field] = {"value": new, "raw": case["extracted"].get(field, {}).get("raw", ""), "score": 1.0}
    _evaluate(case, today, refs)
    save_case(conn, case)
    log_decision(conn, case_id, f"{editor}(수정 후 재검증)", case["engine"], case["decision"], case["reasons"])
    return case


def approve(conn, case_id, editor, final_decision):
    """담당자가 최종 처리(예: '접수', '보완요청')를 확정하고 건을 닫는다."""
    case = get_case(conn, case_id)
    case["status"] = "검토완료"
    save_case(conn, case)
    log_decision(conn, case_id, editor, case["engine"], final_decision, ["담당자 최종 확인"])
    return case
