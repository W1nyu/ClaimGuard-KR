from datetime import date

from PIL import Image

from src.audit import connect, list_decisions, list_edits
from src.pipeline import approve, apply_edits, process_document
from src.route import AUTO, REVIEW_DECISION

TODAY = date(2026, 9, 23)
IMAGE = Image.new("RGB", (2480, 3508), "white")

# 모든 기준 데이터 조회가 통과하는 가짜
PASS_REFS = {
    "diagnosis": lambda n: {"match": "exact", "code": "X", "name": n, "candidates": []},
    "job": lambda n: {"match": "exact", "code": "Y", "name": n, "candidates": []},
    "bank": lambda n: True,
    "address": lambda a: {"status": "found", "road_addr": a},
}

GOOD_VALUES = {
    "피보험자_성명": "홍길동", "주민번호": "900101-1234567", "직업": "사무원", "주소_시도": "서울특별시",
    "주소_시군구": "중구", "주소_도로명": "세종대로", "주소_번지": "110", "연락처": "010-1234-5678",
    "사고_년": "2026", "사고_월": "8", "사고_일": "30", "진단명": "멀미", "계좌번호": "110-123-456789",
    "은행명": "신한", "예금주": "홍길동", "작성_년": "2026", "작성_월": "9", "작성_일": "20", "청구권자": "홍길동",
}


def fake_extractor(scores=None):
    def extract(image, form_code):
        return {k: {"value": v, "raw": v, "score": (scores or {}).get(k, 0.99)} for k, v in GOOD_VALUES.items()}
    return extract


def run(conn=None, engine="paddle", extractors=None, classifier=None):
    return process_document(
        IMAGE, engine=engine, case_id="C1", conn=conn,
        extractors=extractors or {"paddle": fake_extractor(), "claude": fake_extractor()},
        classifier=classifier or (lambda image: ("16", 0.01)), today=TODAY, refs=PASS_REFS,
    )


def test_clean_claim_is_auto_and_logged(tmp_path):
    conn = connect(tmp_path / "a.db")
    case = run(conn)
    assert case["decision"] == AUTO
    assert case["status"] == "처리완료"
    assert [d["actor"] for d in list_decisions(conn, "C1")] == ["AI"]


def test_low_confidence_goes_to_review_queue():
    case = run(extractors={"paddle": fake_extractor({"진단명": 0.4})})
    assert case["decision"] == REVIEW_DECISION
    assert case["status"] == "검토대기"


def test_non_claim_form_goes_to_review_without_extraction():
    case = run(classifier=lambda image: ("12", 0.01))
    assert case["decision"] == REVIEW_DECISION
    assert case["extracted"] == {}
    assert "위임장" in case["reasons"][0]


def test_claude_failure_falls_back_to_paddle():
    def broken(image, form_code):
        raise FileNotFoundError("claude CLI를 찾을 수 없습니다")

    case = run(engine="claude", extractors={"paddle": fake_extractor(), "claude": broken})
    assert case["engine"] == "paddle"
    assert "엔진 A" in case["engine_note"]


def test_edit_revalidates_and_logs(tmp_path):
    conn = connect(tmp_path / "a.db")
    run(conn, extractors={"paddle": fake_extractor({"진단명": 0.4})})
    case = apply_edits(conn, "C1", {"진단명": "멀미"}, editor="담당자A", today=TODAY, refs=PASS_REFS)
    # 담당자가 확인한 칸은 확신도 1.0이 되어 더 이상 검토 사유가 아니다
    assert case["extracted"]["진단명"]["score"] == 1.0
    assert case["decision"] == AUTO
    # 값은 그대로이고 확인만 했으므로 수정 이력은 없고, 재검증 결정이 기록된다
    assert list_edits(conn, "C1") == []
    assert [d["actor"] for d in list_decisions(conn, "C1")] == ["AI", "담당자A(수정 후 재검증)"]


def test_edit_changed_value_is_recorded(tmp_path):
    conn = connect(tmp_path / "a.db")
    run(conn)
    apply_edits(conn, "C1", {"예금주": "김철수"}, editor="담당자A", today=TODAY, refs=PASS_REFS)
    edit = list_edits(conn, "C1")[0]
    assert (edit["field"], edit["old"], edit["new"], edit["editor"]) == ("예금주", "홍길동", "김철수", "담당자A")


def test_approve_closes_case(tmp_path):
    conn = connect(tmp_path / "a.db")
    run(conn, extractors={"paddle": fake_extractor({"진단명": 0.4})})
    case = approve(conn, "C1", editor="담당자A", final_decision="접수")
    assert case["status"] == "검토완료"
    assert list_decisions(conn, "C1")[-1]["decision"] == "접수"
