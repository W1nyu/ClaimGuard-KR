from datetime import date

from src.validate import DOCUMENT, REVIEW, SUPPLEMENT, validate

TODAY = date(2026, 9, 23)

# 기준 데이터 대신 쓰는 가짜 조회 함수들 (파일·네트워크 없이 테스트)
FAKE_REFS = {
    "diagnosis": lambda name: {"match": "exact", "code": "T75.3", "name": name, "candidates": []}
    if name == "멀미" else {"match": "similar", "code": "M60", "name": "근염", "candidates": ["근염"]},
    "job": lambda name: {"match": "exact", "code": "31121", "name": name, "candidates": []}
    if name == "영업 관리 사무원" else {"match": "none", "code": None, "name": None, "candidates": []},
    "bank": lambda name: name in {"신한", "국민은행"},
    "address": lambda address: {"status": "found", "road_addr": address}
    if address.startswith("서울특별시") else {"status": "not_found", "road_addr": None},
}


def good_claim():
    """모든 규칙을 통과하는 청구서(신) 값."""
    return {
        "피보험자_성명": "홍길동", "주민번호": "900101-1234567", "회사명": "가나상사", "부서명": "영업팀",
        "직업": "영업 관리 사무원", "주소_시도": "서울특별시", "주소_시군구": "중구", "주소_도로명": "세종대로",
        "주소_번지": "110", "연락처": "010-1234-5678", "이메일": "hong@example.com",
        "사고_년": "2026", "사고_월": "8", "사고_일": "30", "사고_시": "14", "사고_분": "20",
        "진단명": "멀미", "사고장소": "버스", "치료병원": "가나병원", "사고경위": "버스 이동 중",
        "계좌번호": "110-123-456789", "은행명": "신한", "예금주": "홍길동",
        "작성_년": "2026", "작성_월": "9", "작성_일": "20", "청구권자": "홍길동",
    }


def run(values, form_code="16"):
    return {r["rule"]: r for r in validate(form_code, values, today=TODAY, refs=FAKE_REFS)}


def test_good_claim_passes_every_rule():
    results = run(good_claim())
    assert sorted(results) == ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11"]
    assert all(r["status"] == "pass" for r in results.values())


def test_r01_missing_required_fields():
    values = good_claim()
    values["진단명"] = ""
    del values["계좌번호"]
    r = run(values)["R01"]
    assert r["status"] == "fail" and r["action"] == SUPPLEMENT
    assert r["fields"] == ["진단명", "계좌번호"]


def test_r02_impossible_dates():
    values = good_claim()
    values["사고_년"] = "4925"
    values["작성_월"] = "13"
    r = run(values)["R02"]
    assert r["status"] == "fail" and r["action"] == SUPPLEMENT
    assert "사고일" in r["message"] and "작성일" in r["message"]


def test_r03_accident_after_written_date():
    values = good_claim()
    values["사고_월"], values["사고_일"] = "9", "21"
    r = run(values)["R03"]
    assert r["status"] == "fail" and r["action"] == SUPPLEMENT


def test_r04_older_than_three_years_needs_review():
    values = good_claim()
    values["사고_년"] = "2023"
    values["사고_월"], values["사고_일"] = "9", "19"
    r = run(values)["R04"]
    assert r["status"] == "fail" and r["action"] == REVIEW
    values["사고_일"] = "20"
    assert run(values)["R04"]["status"] == "pass"


def test_r05_resident_number():
    values = good_claim()
    values["주민번호"] = "598096-2264335"  # 96월은 없다
    assert run(values)["R05"]["status"] == "fail"
    values["주민번호"] = "900101-9234567"  # 성별자리 9
    assert run(values)["R05"]["status"] == "fail"
    values["주민번호"] = "0501013234567"  # 하이픈 없이 2005년생
    assert run(values)["R05"]["status"] == "pass"


def test_r06_phone_and_email_format():
    values = good_claim()
    values["연락처"] = "524-7951-4101"
    values["이메일"] = "8mrih9@aazc"
    r = run(values)["R06"]
    assert r["status"] == "fail"
    assert r["fields"] == ["연락처", "이메일"]


def test_r07_address_not_found_and_unavailable():
    values = good_claim()
    values["주소_시도"] = "세종특별자치시"
    assert run(values)["R07"]["status"] == "fail"
    refs = dict(FAKE_REFS, address=lambda a: {"status": "unavailable", "road_addr": None})
    r = {x["rule"]: x for x in validate("16", good_claim(), today=TODAY, refs=refs)}["R07"]
    assert r["status"] == "unknown" and r["action"] == REVIEW


def test_r08_similar_diagnosis_needs_review_with_candidates():
    values = good_claim()
    values["진단명"] = "근엄"
    r = run(values)["R08"]
    assert r["status"] == "fail" and r["action"] == REVIEW
    assert "근염" in r["message"]
    assert run(good_claim())["R08"]["detail"]["code"] == "T75.3"


def test_r09_unknown_job_needs_review():
    values = good_claim()
    values["직업"] = "검투사"
    r = run(values)["R09"]
    assert r["status"] == "fail" and r["action"] == REVIEW


def test_r10_bank_and_account():
    values = good_claim()
    values["은행명"] = "무궁"
    values["계좌번호"] = "123-45"
    r = run(values)["R10"]
    assert r["status"] == "fail" and r["action"] == SUPPLEMENT
    assert r["fields"] == ["은행명", "계좌번호"]


def test_r11_other_account_holder_needs_documents():
    values = good_claim()
    values["예금주"] = "김철수"
    r = run(values)["R11"]
    assert r["status"] == "fail" and r["action"] == DOCUMENT
    assert "위임장" in r["message"]


def test_old_form_uses_two_digit_claim_year():
    values = {
        "보험종목": "펫보험", "증권번호": "1234567890123", "계약자": "홍길동", "사고일자": "2026.8.30",
        "사고원인": "질병", "사고경위": "구토", "청구_년": "26", "청구_월": "9", "청구_일": "20",
        "청구인_성명": "홍길동", "주소_시도": "서울특별시", "주소_시군구": "중구", "연락처": "010-1234-5678",
    }
    results = run(values, form_code="15")
    assert sorted(results) == ["R01", "R02", "R03", "R04", "R06", "R07"]
    assert all(r["status"] == "pass" for r in results.values())
    values["사고일자"] = "7907.2.20"
    assert run(values, form_code="15")["R02"]["status"] == "fail"
