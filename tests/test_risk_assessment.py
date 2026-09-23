import pytest

from src.risk_assessment import ITEMS, SCENARIOS, assess, grade, report_markdown, required_controls

# 가이드라인 15쪽 예시표의 '위험 경감' 점수 (항목: 경감 점수). 잔여 위험 합계는 54점이어야 한다.
GUIDELINE_EXAMPLE_MITIGATION = {
    "금융소비자보호법 위반 가능성": 4, "인공지능기본법 위반 가능성": 3, "데이터 관련법 위반 가능성": 2,
    "개별 업권법 위반 가능성": 2, "품질": 4, "편향성": 2, "공정성": 2, "설명가능성": 1, "성능": 3,
    "계약 권리 침해": 3, "책임 투명성": 3, "소비자 보호 방안": 4, "보안": 3, "안정성": 4, "위탁·관리": 3,
    "프라이버시": 3,
}


def test_items_total_100_with_guideline_weights():
    assert sum(i["points"] for i in ITEMS) == 100
    by_principle = {}
    for i in ITEMS:
        by_principle[i["principle"]] = by_principle.get(i["principle"], 0) + i["points"]
    assert by_principle == {"합법성": 20, "신뢰성": 30, "신의성실": 20, "보안성": 30}
    assert len(ITEMS) == 16


def test_guideline_example_is_54_points_high_risk():
    points = {i["item"]: i["points"] for i in ITEMS}
    rates = {item: mitigated / points[item] for item, mitigated in GUIDELINE_EXAMPLE_MITIGATION.items()}
    result = assess(rates)
    assert result["total"] == pytest.approx(54)
    assert result["grade"] == "고위험"
    assert result["by_principle"] == pytest.approx({"합법성": 9, "신뢰성": 18, "신의성실": 10, "보안성": 17})
    assert result["committee_review"] is False


def test_grade_boundaries():
    assert grade(24.9) == "저위험"
    assert grade(25) == "중위험"
    assert grade(49.9) == "중위험"
    assert grade(50) == "고위험"
    assert grade(75) == "고위험"


def test_no_mitigation_means_committee_review():
    result = assess({})
    assert result["total"] == 100
    assert result["committee_review"] is True


def test_rate_out_of_range_is_error():
    with pytest.raises(ValueError):
        assess({"품질": 1.2})
    with pytest.raises(ValueError):
        assess({"없는 항목": 0.5})


def test_required_controls_grow_with_grade():
    assert len(required_controls("고위험")) > len(required_controls("중위험")) > len(required_controls("저위험"))


def test_scenarios_cover_all_items_and_external_model_is_riskier():
    names = {i["item"] for i in ITEMS}
    totals = {}
    for name, scenario in SCENARIOS.items():
        assert set(scenario) == names
        for rate, evidence in scenario.values():
            assert 0 <= rate <= 1 and evidence
        totals[name] = assess({item: rate for item, (rate, _) in scenario.items()})["total"]
    local, external = list(totals)
    assert totals[external] > totals[local]


def test_report_contains_grade_and_evidence():
    name, scenario = next(iter(SCENARIOS.items()))
    result = assess({item: rate for item, (rate, _) in scenario.items()})
    evidence = {item: text for item, (_, text) in scenario.items()}
    report = report_markdown(name, result, evidence)
    assert result["grade"] in report
    assert evidence["책임 투명성"] in report
    assert "평가자 판단" in report
