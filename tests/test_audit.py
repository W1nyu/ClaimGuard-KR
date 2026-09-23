from src.audit import (
    connect, get_case, list_cases, list_decisions, list_edits, log_decision, log_edit, save_case,
)


def sample_case(case_id="C1", status="검토대기"):
    return {
        "case_id": case_id, "form_code": "16", "engine": "paddle", "engine_note": "",
        "extracted": {"진단명": {"value": "근엄", "raw": "근엄", "score": 0.6}},
        "values": {"진단명": "근엄"}, "rules": [], "decision": "담당자검토",
        "reasons": ["[R08] 문제"], "customer_message": None, "low_confidence_fields": ["진단명"],
        "status": status,
    }


def test_save_and_get_case_round_trip(tmp_path):
    conn = connect(tmp_path / "audit.db")
    save_case(conn, sample_case())
    case = get_case(conn, "C1")
    assert case["values"] == {"진단명": "근엄"}
    assert case["extracted"]["진단명"]["score"] == 0.6
    assert case["reasons"] == ["[R08] 문제"]
    assert get_case(conn, "없음") is None


def test_save_case_updates_existing(tmp_path):
    conn = connect(tmp_path / "audit.db")
    save_case(conn, sample_case())
    save_case(conn, sample_case(status="검토완료"))
    assert [c["status"] for c in list_cases(conn)] == ["검토완료"]


def test_list_cases_filters_by_status(tmp_path):
    conn = connect(tmp_path / "audit.db")
    save_case(conn, sample_case("C1", "검토대기"))
    save_case(conn, sample_case("C2", "처리완료"))
    assert [c["case_id"] for c in list_cases(conn, status="검토대기")] == ["C1"]


def test_decisions_and_edits_are_logged_in_order(tmp_path):
    conn = connect(tmp_path / "audit.db")
    log_decision(conn, "C1", "AI", "paddle", "담당자검토", ["[R08] 문제"])
    log_edit(conn, "C1", "진단명", "근엄", "근염", "담당자A")
    log_decision(conn, "C1", "담당자A", "paddle", "보완요청", ["담당자 확인"])
    decisions = list_decisions(conn, "C1")
    assert [d["actor"] for d in decisions] == ["AI", "담당자A"]
    assert decisions[0]["reasons"] == ["[R08] 문제"]
    edits = list_edits(conn)
    assert edits[0]["field"] == "진단명" and edits[0]["old"] == "근엄" and edits[0]["new"] == "근염"
    assert "at" in edits[0]
