from src.route import AUTO, REVIEW_DECISION, SUPPLEMENT_DECISION, decide


def rule(rule_id, status, action, message="문제"):
    return {"rule": rule_id, "status": status, "fields": [], "message": message if status != "pass" else "",
            "action": action, "detail": {}}


def test_all_pass_is_auto():
    result = decide([rule("R01", "pass", "보완요청"), rule("R08", "pass", "담당자검토")])
    assert result["decision"] == AUTO
    assert result["reasons"] == []
    assert result["customer_message"] is None


def test_customer_fixable_problem_is_supplement_with_message():
    result = decide([
        rule("R06", "fail", "보완요청", "형식이 올바르지 않습니다: 연락처"),
        rule("R11", "fail", "추가서류", "위임장과 인감증명서가 필요합니다"),
    ])
    assert result["decision"] == SUPPLEMENT_DECISION
    assert result["reasons"] == ["[R06] 형식이 올바르지 않습니다: 연락처", "[R11] 위임장과 인감증명서가 필요합니다"]
    assert "1. 형식이 올바르지 않습니다: 연락처" in result["customer_message"]
    assert "2. 위임장과 인감증명서가 필요합니다" in result["customer_message"]


def test_review_rule_wins_over_supplement():
    result = decide([rule("R06", "fail", "보완요청"), rule("R08", "fail", "담당자검토")])
    assert result["decision"] == REVIEW_DECISION
    # 담당자가 고객에게 보낼 수 있도록 안내문은 그대로 만든다
    assert result["customer_message"] is not None


def test_unknown_status_goes_to_review():
    assert decide([rule("R07", "unknown", "담당자검토")])["decision"] == REVIEW_DECISION


def test_low_confidence_filled_field_goes_to_review():
    extracted = {
        "성명": {"value": "홍길동", "score": 0.99},
        "진단명": {"value": "근엄", "score": 0.61},
        "이메일": {"value": "", "score": 0.10},  # 빈칸은 확신도를 보지 않는다
    }
    result = decide([rule("R01", "pass", "보완요청")], extracted=extracted)
    assert result["decision"] == REVIEW_DECISION
    assert result["low_confidence_fields"] == ["진단명"]
    assert result["reasons"] == ["[확신도] '진단명' 칸 확신도 0.61 < 0.85"]


def test_threshold_is_adjustable():
    extracted = {"진단명": {"value": "근염", "score": 0.61}}
    assert decide([], extracted=extracted, threshold=0.5)["decision"] == AUTO
