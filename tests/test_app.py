"""각 화면이 오류 없이 뜨는지 Streamlit AppTest로 확인한다."""
import pytest
from streamlit.testing.v1 import AppTest

from src.audit import connect, log_decision, save_case
from src.load_data import PROJECT_ROOT

PAGES = ["app.py", "pages/1_청구_접수.py", "pages/2_청구_검토.py", "pages/3_서류_접수.py", "pages/4_서류_검토.py",
         "pages/5_성능_비교.py", "pages/6_AI_위험평가.py", "pages/7_감사_로그.py"]


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    path = tmp_path / "audit.db"
    monkeypatch.setenv("CLAIM_AUDIT_DB", str(path))
    return path


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_error(page):
    at = AppTest.from_file(str(PROJECT_ROOT / page), default_timeout=60).run()
    assert not at.exception


def test_review_queue_shows_waiting_case(temp_db):
    conn = connect(temp_db)
    save_case(conn, {
        "case_id": "C1", "form_code": "16", "engine": "paddle", "engine_note": "",
        "extracted": {"진단명": {"value": "근엄", "raw": "근엄", "score": 0.6}}, "values": {"진단명": "근엄"},
        "rules": [], "decision": "담당자검토", "reasons": ["[확신도] '진단명' 칸 확신도 0.60 < 0.85"],
        "customer_message": None, "low_confidence_fields": ["진단명"], "status": "검토대기",
    })
    log_decision(conn, "C1", "AI", "paddle", "담당자검토", ["x"])
    at = AppTest.from_file(str(PROJECT_ROOT / "pages/4_서류_검토.py"), default_timeout=60).run()
    assert not at.exception
    assert "검토 대기 1건" in [m.value for m in at.markdown]


def test_claim_review_page_shows_waiting_claim_and_rejudges(temp_db):
    from datetime import date

    from src.audit import get_claim
    from src.bundle import evaluate_claim
    from src.audit import save_claim
    conn = connect(temp_db)
    entries = [{"declared_type": "보험금청구서", "classified_type": "보험금청구서", "form_code": "16", "engine": "paddle",
                "engine_note": "", "rules": [],
                "values": {"예금주": "김철수", "피보험자_성명": "홍길동"},
                "extracted": {"예금주": {"value": "김철수", "raw": "김철수", "score": 0.4},
                              "피보험자_성명": {"value": "홍길동", "raw": "홍길동", "score": 0.99}}}]
    claim = {"type": "질병", "items": [], "inpatient_under_50": False, "noncovered_or_manual": False,
             "injury_cause": None, "delegation": False, "family_check": False, "beneficiary_unspecified": False}
    refs = {"diagnosis": lambda n: {"match": "exact", "code": "X", "name": n, "candidates": []},
            "job": lambda n: {"match": "exact", "code": "Y", "name": n, "candidates": []},
            "bank": lambda n: True, "address": lambda a: {"status": "found", "road_addr": a}}
    bundle = evaluate_claim(claim, entries, "C9", today=date(2026, 9, 24), refs=refs)
    save_claim(conn, bundle)
    assert bundle["status"] == "검토대기"
    at = AppTest.from_file(str(PROJECT_ROOT / "pages/2_청구_검토.py"), default_timeout=60).run()
    assert not at.exception
    assert "검토 대기 1건" in [m.value for m in at.markdown]
    # 위임 판단 라디오가 보인다 (B01 확인 필요)
    assert any("위임" in r.label for r in at.radio)
