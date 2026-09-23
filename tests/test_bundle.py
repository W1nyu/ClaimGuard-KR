from datetime import date

from PIL import Image

from src.audit import connect, list_decisions
from src.bundle import process_claim
from src.route import AUTO, REVIEW_DECISION, SUPPLEMENT_DECISION

TODAY = date(2026, 9, 23)
PASS_REFS = {
    "diagnosis": lambda n: {"match": "exact", "code": "X", "name": n, "candidates": []},
    "job": lambda n: {"match": "exact", "code": "Y", "name": n, "candidates": []},
    "bank": lambda n: True,
    "address": lambda a: {"status": "found", "road_addr": a},
}
CLAIM_FORM = {
    "피보험자_성명": "홍길동", "주민번호": "900101-1234567", "직업": "사무원", "주소_시도": "서울특별시",
    "주소_시군구": "중구", "주소_도로명": "세종대로", "주소_번지": "110", "연락처": "010-1234-5678",
    "사고_년": "2026", "사고_월": "8", "사고_일": "30", "진단명": "멀미", "사고경위": "버스 이동 중",
    "계좌번호": "110-123-456789", "은행명": "신한", "예금주": "홍길동",
    "작성_년": "2026", "작성_월": "9", "작성_일": "20", "청구권자": "홍길동",
}
POWER_OF_ATTORNEY = {
    "위임사항_피보험자": "홍길동", "사고_년": "2026", "사고_월": "8", "사고_일": "30",
    "수임인_성명": "김철수", "수임인_은행명": "신한", "수임인_계좌번호": "110-999-000000",
}


def image(form_code):
    # 가짜 분류기가 이미지 크기로 양식을 알아보게 한다
    return Image.new("RGB", (10, int(form_code)), "white")


def fake_classifier(img):
    return str(img.size[1]), 0.01


def fake_extractors(claim_overrides=None, poa_overrides=None, low=()):
    values = {"16": {**CLAIM_FORM, **(claim_overrides or {})}, "12": {**POWER_OF_ATTORNEY, **(poa_overrides or {})}}

    def extract(img, form_code):
        return {k: {"value": v, "raw": v, "score": 0.4 if k in low else 0.99} for k, v in values[form_code].items()}
    return {"paddle": extract, "claude": extract}


def claim_info(**overrides):
    base = {"type": "질병", "items": ["실손_통원"], "inpatient_under_50": False, "noncovered_or_manual": False,
            "injury_cause": None, "delegation": False, "family_check": False, "beneficiary_unspecified": False}
    base.update(overrides)
    return base


OUTPATIENT_DOCS = [{"declared_type": t, "image": None} for t in
                   ["개인(신용)정보처리동의서", "신분증 사본", "진료비계산영수증", "진료비세부내역서", "처방전"]]


def run(documents, claim=None, extractors=None, conn=None):
    return process_claim(claim or claim_info(), documents, case_id="B1", conn=conn,
                         extractors=extractors or fake_extractors(), classifier=fake_classifier,
                         today=TODAY, refs=PASS_REFS)


def test_complete_outpatient_claim_is_auto(tmp_path):
    conn = connect(tmp_path / "a.db")
    docs = [{"declared_type": "보험금청구서", "image": image("16")}] + OUTPATIENT_DOCS
    result = run(docs, conn=conn)
    assert result["missing"] == []
    assert result["decision"] == AUTO
    assert list_decisions(conn, "B1")[0]["decision"] == AUTO


def test_missing_document_is_supplement_with_issuer():
    docs = [{"declared_type": "보험금청구서", "image": image("16")}] + OUTPATIENT_DOCS[:3]
    result = run(docs)
    assert [m["name"] for m in result["missing"]] == ["진료비세부내역서", "진단명 포함 서류"]
    assert result["decision"] == SUPPLEMENT_DECISION
    assert "진료비세부내역서" in result["customer_message"] and "의료기관" in result["customer_message"]


def test_other_account_holder_adds_delegation_documents_automatically():
    docs = [{"declared_type": "보험금청구서", "image": image("16")}] + OUTPATIENT_DOCS
    result = run(docs, extractors=fake_extractors(claim_overrides={"예금주": "김철수"}))
    assert result["effective_claim"]["delegation"] is True
    missing = [m["name"] for m in result["missing"]]
    assert missing == ["위임장", "청구권자 개인(신용)정보처리동의서", "인감증명서"]
    assert any(c["rule"] == "B01" for c in result["checks"])


def test_power_of_attorney_matches_claim_form():
    docs = ([{"declared_type": "보험금청구서", "image": image("16")}, {"declared_type": "위임장", "image": image("12")}]
            + OUTPATIENT_DOCS
            + [{"declared_type": t, "image": None} for t in ["청구권자 개인(신용)정보처리동의서", "인감증명서"]])
    result = run(docs, extractors=fake_extractors(claim_overrides={"예금주": "김철수", "계좌번호": "110-999-000000"}))
    checks = {c["rule"]: c["status"] for c in result["checks"]}
    assert checks["B02"] == "pass" and checks["B03"] == "pass" and checks["B04"] == "pass" and checks["B05"] == "pass"
    assert result["missing"] == []
    assert result["decision"] == AUTO


def test_power_of_attorney_mismatch_is_flagged():
    docs = ([{"declared_type": "보험금청구서", "image": image("16")}, {"declared_type": "위임장", "image": image("12")}]
            + OUTPATIENT_DOCS)
    result = run(docs, extractors=fake_extractors(claim_overrides={"예금주": "김철수"},
                                                  poa_overrides={"수임인_성명": "이영희", "사고_일": "31"}))
    checks = {c["rule"]: c for c in result["checks"]}
    assert checks["B02"]["status"] == "fail" and "이영희" in checks["B02"]["message"]
    assert checks["B05"]["status"] == "fail"
    # OCR로 읽은 두 서류의 불일치는 OCR 오류일 수 있어 고객에게 바로 보내지 않고 담당자가 확인한다
    assert checks["B02"]["action"] == "담당자검토"
    assert result["decision"] == REVIEW_DECISION
    assert "이영희" not in (result["customer_message"] or "")


def test_declared_type_different_from_classified_needs_review():
    docs = [{"declared_type": "위임장", "image": image("16")}] + OUTPATIENT_DOCS
    result = run(docs)
    b06 = [c for c in result["checks"] if c["rule"] == "B06"][0]
    assert b06["status"] == "fail" and "보험금청구서" in b06["message"]
    assert result["decision"] == REVIEW_DECISION


def test_low_confidence_on_document_goes_to_review():
    docs = [{"declared_type": "보험금청구서", "image": image("16")}] + OUTPATIENT_DOCS
    result = run(docs, extractors=fake_extractors(low=("예금주",)))
    assert result["decision"] == REVIEW_DECISION
    assert "보험금청구서:예금주" in result["low_confidence_fields"]


def test_injury_without_proof_needs_detailed_accident_description():
    docs = [{"declared_type": "보험금청구서", "image": image("16")}, {"declared_type": "병원 초진차트", "image": None}] \
        + OUTPATIENT_DOCS
    result = run(docs, claim=claim_info(type="상해", injury_cause="발급불가"),
                 extractors=fake_extractors(claim_overrides={"사고경위": ""}))
    b07 = [c for c in result["checks"] if c["rule"] == "B07"][0]
    assert b07["status"] == "fail" and "육하원칙" in b07["message"]


def test_low_confidence_names_do_not_auto_add_delegation_documents():
    docs = [{"declared_type": "보험금청구서", "image": image("16")}] + OUTPATIENT_DOCS
    result = run(docs, extractors=fake_extractors(claim_overrides={"예금주": "김철수"}, low=("예금주",)))
    b01 = [c for c in result["checks"] if c["rule"] == "B01"][0]
    assert b01["status"] == "unknown" and "위임 여부" in b01["message"]
    assert result["effective_claim"]["delegation"] is False
    assert "위임장" not in [m["name"] for m in result["missing"]]
    assert result["decision"] == REVIEW_DECISION
