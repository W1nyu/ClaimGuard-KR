from src.claim_docs import check_completeness, issuer_of, required_documents


def claim(**overrides):
    base = {"type": "질병", "items": [], "inpatient_under_50": False, "noncovered_or_manual": False,
            "injury_cause": None, "delegation": False, "family_check": False, "beneficiary_unspecified": False}
    base.update(overrides)
    return base


def names(requirements):
    return [r["name"] for r in requirements]


def test_common_documents_always_required():
    assert names(required_documents(claim())) == ["보험금청구서", "개인(신용)정보처리동의서", "신분증 사본"]


def test_inpatient_allows_substitute_only_under_500k():
    over = {r["name"]: r["any_of"] for r in required_documents(claim(items=["실손_입원"]))}
    assert over["진단서"] == ["진단서"]
    under = {r["name"]: r["any_of"] for r in required_documents(claim(items=["실손_입원"], inpatient_under_50=True))}
    assert under["진단서"] == ["진단서", "입퇴원확인서", "진료확인서"]
    assert "진료비계산영수증" in under and "진료비세부내역서" in under


def test_outpatient_needs_document_with_diagnosis_code():
    reqs = {r["name"]: r for r in required_documents(claim(items=["실손_통원"]))}
    assert "진단서" in reqs["진단명 포함 서류"]["any_of"] and "처방전" in reqs["진단명 포함 서류"]["any_of"]


def test_manual_therapy_makes_itemized_bill_mandatory_with_reason():
    reqs = {r["name"]: r for r in required_documents(claim(items=["실손_통원"], noncovered_or_manual=True))}
    assert "도수치료" in reqs["진료비세부내역서"]["reason"]


def test_injury_needs_accident_proof_by_cause():
    by_cause = {
        "교통사고": ["사고사실확인서"],
        "산재": ["요양급여신청서", "보험급여지급확인원"],
        "발급불가": ["병원 초진차트"],
    }
    for cause, expected in by_cause.items():
        reqs = {r["name"]: r for r in required_documents(claim(type="상해", injury_cause=cause))}
        assert reqs["상해사고 입증서류"]["any_of"] == expected
    # 질병 청구에는 사고 입증서류가 없다
    assert "상해사고 입증서류" not in names(required_documents(claim(type="질병")))


def test_delegation_adds_three_documents():
    added = names(required_documents(claim(delegation=True)))[3:]
    assert added == ["위임장", "청구권자 개인(신용)정보처리동의서", "인감증명서"]


def test_death_without_beneficiary_needs_inheritance_documents():
    reqs = names(required_documents(claim(items=["사망"], beneficiary_unspecified=True)))
    assert "사망진단서" in reqs and "기본증명서" in reqs and "상속관계 확인서류" in reqs


def test_same_document_is_listed_once_with_merged_reasons():
    reqs = [r for r in required_documents(claim(items=["진단_암", "진단_기타"])) if r["name"] == "진단서"]
    assert len(reqs) == 1
    assert "암" in reqs[0]["reason"] and "기타" in reqs[0]["reason"]


def test_every_requirement_cites_db_source():
    reqs = required_documents(claim(type="상해", items=["실손_입원", "수술", "후유장해"], injury_cause="교통사고",
                                    delegation=True, family_check=True))
    assert all(r["source"].startswith("https://www.idbins.com/") for r in reqs)


def test_check_completeness_accepts_any_alternative():
    reqs = required_documents(claim(items=["실손_입원"], inpatient_under_50=True))
    submitted = {"보험금청구서", "개인(신용)정보처리동의서", "신분증 사본", "입퇴원확인서", "진료비계산영수증"}
    missing = check_completeness(reqs, submitted)
    assert [m["name"] for m in missing] == ["진료비세부내역서"]
    assert missing[0]["issuer"] == "의료기관"


def test_issuer_lookup():
    assert issuer_of("인감증명서") == "관공서(주민센터)"
    assert issuer_of("위임장") == "보험회사"
