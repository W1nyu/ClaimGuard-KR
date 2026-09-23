"""보험금 청구 구비서류 규칙표 (장기보험 질병·상해).

출처: DB손해보험 홈페이지 '보험금청구서류 안내' (2026.9.23 원문 확인)
- 질병관련사고: https://www.idbins.com/pc/bizxpress/ct/dc/FWCUSV1301.shtm
- 상해/운행관련사고: https://www.idbins.com/pc/bizxpress/ct/dc/FWCUSV1300.shtm
안내의 '보장내역 → 청구서류 → 발급처' 표를 청구 정보(유형·항목·조건)에 따라 필요한 서류 목록으로 바꾼다.
"""

DISEASE_SOURCE = "https://www.idbins.com/pc/bizxpress/ct/dc/FWCUSV1301.shtm"
INJURY_SOURCE = "https://www.idbins.com/pc/bizxpress/ct/dc/FWCUSV1300.shtm"

# 서류 종류 → 발급처 (안내 표의 '발급처' 열)
ISSUERS = {
    "보험금청구서": "보험회사", "개인(신용)정보처리동의서": "보험회사", "신분증 사본": "본인",
    "위임장": "보험회사", "청구권자 개인(신용)정보처리동의서": "보험회사",
    "인감증명서": "관공서(주민센터)", "본인서명사실확인서": "관공서(주민센터)",
    "가족관계증명서": "관공서(주민센터)", "혼인관계증명서": "관공서(주민센터)", "주민등록등본": "관공서(주민센터)",
    "기본증명서": "관공서(주민센터)",
    "사고사실확인서": "공공기관(경찰서·소방서)·보험회사·공제조합",
    "요양급여신청서": "근로복지공단", "보험급여지급확인원": "근로복지공단",
    "공무상병인증서": "군부대", "법원 판결문": "법원",
}
MEDICAL = "의료기관"

# 고객이 고를 수 있는 청구 항목
CLAIM_ITEMS = {
    "실손_입원": "실손의료비(입원)", "실손_통원": "실손의료비(통원)", "입원일당": "입원일당",
    "수술": "수술", "진단_암": "진단(암)", "진단_뇌": "진단(뇌질환)", "진단_심": "진단(심질환)",
    "진단_기타": "진단(기타)", "사망": "사망", "후유장해": "후유장해",
}
INJURY_CAUSES = {
    "교통사고": ["사고사실확인서"],
    "산재": ["요양급여신청서", "보험급여지급확인원"],
    "군복무": ["공무상병인증서"],
    "법원분쟁": ["법원 판결문"],
    "기타": ["사고사실확인서"],
    # 사고확인서류 발급 불가: 초진차트 + 청구서 사고내용 육하원칙 상세기재
    "발급불가": ["병원 초진차트"],
}
DIAGNOSIS_CODE_DOCS = ["진단서", "통원확인서", "처방전", "진료확인서", "소견서", "진료차트"]


def issuer_of(document):
    return ISSUERS.get(document, MEDICAL)


def _req(name, any_of, reason, source):
    return {"name": name, "any_of": list(any_of), "reason": reason, "source": source}


def _item_requirements(item, claim, source):
    """청구 항목 하나에 필요한 서류들."""
    if item == "실손_입원":
        diagnosis = ["진단서"]
        reason = "실손의료비(입원)"
        if claim["inpatient_under_50"]:
            # 50만원 이하: 진단명 포함 입퇴원확인서 또는 진단명·입원기간 포함 진료확인서로 대체 가능
            diagnosis += ["입퇴원확인서", "진료확인서"]
            reason += " — 50만원 이하라 입퇴원확인서·진료확인서로 대체 가능"
        itemized = "실손의료비(입원)"
        return [_req("진단서", diagnosis, reason, source),
                _req("진료비계산영수증", ["진료비계산영수증"], "실손의료비(입원)", source),
                _req("진료비세부내역서", ["진료비세부내역서"], _itemized_reason(itemized, claim), source)]
    if item == "실손_통원":
        return [_req("진료비계산영수증", ["진료비계산영수증"], "실손의료비(통원)", source),
                _req("진료비세부내역서", ["진료비세부내역서"], _itemized_reason("실손의료비(통원)", claim), source),
                _req("진단명 포함 서류", DIAGNOSIS_CODE_DOCS, "실손의료비(통원) — 진단명(질병분류코드) 기재 필수", source)]
    if item == "입원일당":
        return [_req("진단명·입원기간 포함 서류", ["입퇴원확인서", "진단서"], "입원일당", source)]
    if item == "수술":
        return [_req("진단명·수술명·수술일자 포함 서류", ["수술확인서", "수술기록지", "진단서"], "수술", source)]
    if item == "진단_암":
        return [_req("진단서", ["진단서"], "진단(암)", source),
                _req("조직검사결과지", ["조직검사결과지"], "진단(암)", source)]
    if item == "진단_뇌":
        return [_req("진단서", ["진단서"], "진단(뇌질환)", source),
                _req("방사선 판독결과지", ["방사선 판독결과지"], "진단(뇌질환) — CT·MRI 등", source)]
    if item == "진단_심":
        return [_req("진단서", ["진단서"], "진단(심질환)", source),
                _req("검사결과지", ["검사결과지"], "진단(심질환) — 관상동맥 조영술·심전도 등", source)]
    if item == "진단_기타":
        return [_req("진단서", ["진단서"], "진단(기타)", source)]
    if item == "사망":
        reqs = [_req("사망진단서", ["사망진단서", "시체검안서"], "사망", source),
                _req("기본증명서", ["기본증명서"], "사망 — 사망사실 기재", source)]
        if claim["beneficiary_unspecified"]:
            reqs.append(_req("상속관계 확인서류", ["가족관계증명서", "혼인관계증명서"], "사망 — 수익자 미지정", source))
        return reqs
    if item == "후유장해":
        return [_req("후유장해진단서", ["후유장해진단서"], "후유장해 — 발급 전 콜센터·지급담당자와 상의 권장", source)]
    raise ValueError(f"알 수 없는 청구 항목: {item}")


def _itemized_reason(base, claim):
    if claim["noncovered_or_manual"]:
        return f"{base} — 비급여 항목·도수치료가 있어 반드시 제출"
    return base


def _merge(requirements):
    """같은 서류가 여러 항목에서 요구되면 한 번만 남기고, 대체 가능 서류는 가장 엄격한 쪽(교집합)을 따른다."""
    merged = {}
    for req in requirements:
        if req["name"] not in merged:
            merged[req["name"]] = dict(req, any_of=list(req["any_of"]))
            continue
        kept = merged[req["name"]]
        kept["any_of"] = [d for d in kept["any_of"] if d in req["any_of"]] or kept["any_of"]
        if req["reason"] not in kept["reason"]:
            kept["reason"] += f" / {req['reason']}"
    return list(merged.values())


def required_documents(claim):
    """청구 정보로 필요한 서류 목록을 만든다.

    claim 키: type(질병/상해), items(CLAIM_ITEMS 키 목록), inpatient_under_50, noncovered_or_manual,
    injury_cause(상해일 때 INJURY_CAUSES 키), delegation, family_check, beneficiary_unspecified
    """
    source = INJURY_SOURCE if claim["type"] == "상해" else DISEASE_SOURCE
    reqs = [
        _req("보험금청구서", ["보험금청구서"], "공통 (계좌번호 포함)", source),
        _req("개인(신용)정보처리동의서", ["개인(신용)정보처리동의서"], "공통", source),
        _req("신분증 사본", ["신분증 사본"], "공통", source),
    ]
    if claim["family_check"]:
        reqs.append(_req("가족관계 확인서류", ["가족관계증명서", "혼인관계증명서", "주민등록등본"],
                         "배우자·자녀 보장상품 또는 수익자 미성년", source))
    if claim["delegation"]:
        reqs += [
            _req("위임장", ["위임장"], "타인에게 보험금 위임", source),
            _req("청구권자 개인(신용)정보처리동의서", ["청구권자 개인(신용)정보처리동의서"], "타인에게 보험금 위임", source),
            _req("인감증명서", ["인감증명서", "본인서명사실확인서"], "타인에게 보험금 위임", source),
        ]
    for item in claim["items"]:
        reqs += _item_requirements(item, claim, source)
    if claim["type"] == "상해":
        cause = claim.get("injury_cause") or "기타"
        reason = f"상해사고 입증 — {cause}"
        if cause == "발급불가":
            reason += " (청구서 사고내용을 육하원칙에 따라 상세 기재)"
        reqs.append(_req("상해사고 입증서류", INJURY_CAUSES[cause], reason, source))
    return _merge(reqs)


def check_completeness(requirements, submitted):
    """제출 서류 종류 집합과 비교해 빠진 서류를 발급처와 함께 돌려준다. 대체 서류 중 하나만 있으면 된다."""
    missing = []
    for req in requirements:
        if not any(doc in submitted for doc in req["any_of"]):
            missing.append({**req, "issuer": issuer_of(req["any_of"][0])})
    return missing
