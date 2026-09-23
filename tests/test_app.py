"""각 화면이 오류 없이 뜨는지 Streamlit AppTest로 확인한다."""
import pytest
from streamlit.testing.v1 import AppTest

from src.audit import connect, log_decision, save_case
from src.load_data import PROJECT_ROOT

PAGES = ["app.py", "pages/1_서류_접수.py", "pages/2_검토_대기함.py", "pages/3_성능_비교.py", "pages/5_감사_로그.py"]


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
    at = AppTest.from_file(str(PROJECT_ROOT / "pages/2_검토_대기함.py"), default_timeout=60).run()
    assert not at.exception
    assert "검토 대기 1건" in [m.value for m in at.markdown]
