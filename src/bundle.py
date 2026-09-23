"""청구 건 단위 처리: 청구 정보 + 서류 묶음 → 구비서류 완비 판단 + 청구서·위임장 대조 + 건 결정.

- 이미지가 있는 서류(보험금청구서, 위임장)는 분류·추출한다. 청구서는 기존 검증 규칙(R01~R10)도 적용한다.
- 의료기관·관공서 서류는 공개 데이터에 이미지가 없어 고객이 고른 서류 종류만 받고 내용은 읽지 않는다.
- 청구서의 예금주가 피보험자와 다르면 위임 서류를 필요 목록에 자동으로 넣는다(단건 규칙 R11을 대신함).

건 단위 규칙
  D01 필요 서류 누락                         → 보완요청 (서류명·발급처 안내)
  B01 예금주 ≠ 피보험자 → 위임 서류 자동 추가  (안내)
  B02 위임장 수임인 = 청구서 예금주            → 불일치 시 보완요청
  B03 위임장 수령계좌·은행 = 청구서 계좌·은행   → 불일치 시 보완요청
  B04 위임장 피보험자 = 청구서 피보험자         → 불일치 시 보완요청
  B05 위임장 사고일 = 청구서 사고일            → 불일치 시 보완요청
  B06 고객이 고른 서류 종류 ≠ 판별된 양식       → 담당자검토
  B07 상해 사고확인서류 발급불가인데 사고경위가 비어 있음 → 보완요청
"""
import re
import uuid

from src.audit import log_decision, save_claim
from src.claim_docs import check_completeness, required_documents
from src.load_data import FORM_NAMES
from src.pipeline import _default_classifier, _default_extractors, process_document
from src.reference import normalize_name
from src.route import REVIEW_DECISION, decide
from src.validate import DOCUMENT, REVIEW, SUPPLEMENT

# 판별된 양식 코드 → 구비서류 규칙표의 서류 이름
FORM_DOC_TYPE = {"15": "보험금청구서", "16": "보험금청구서", "12": "위임장"}


def _check(rule, status, fields, message, action, detail=None):
    return {"rule": rule, "status": status, "fields": fields, "message": message if status != "pass" or rule == "B01" else "",
            "action": action, "detail": detail or {}}


def _doc_type(form_code):
    if form_code in FORM_DOC_TYPE:
        return FORM_DOC_TYPE[form_code]
    return FORM_NAMES.get(form_code)


def _extract(image, form_code, engine, extractors):
    """엔진으로 추출하고, 엔진 B가 실패하면 엔진 A로 대신한다."""
    try:
        return extractors[engine](image, form_code), engine, ""
    except Exception as error:
        if engine == "paddle":
            raise
        return extractors["paddle"](image, form_code), "paddle", f"엔진 B 실패로 엔진 A 사용: {error}"


def _same(a, b):
    return normalize_name(a) == normalize_name(b)


def _digits(text):
    return re.sub(r"\D", "", text or "")


def _date_key(year, month, day):
    try:
        return int(year), int(month), int(day)
    except (TypeError, ValueError):
        return normalize_name(f"{year}-{month}-{day}")


def _compare(rule, label, claim_value, poa_value, fields, equal):
    if not claim_value or not poa_value:
        return _check(rule, "unknown", fields, f"{label}: 비교할 값이 비어 있어 확인하지 못했습니다", REVIEW)
    if equal:
        return _check(rule, "pass", fields, "", SUPPLEMENT)
    return _check(rule, "fail", fields,
                  f"{label} 불일치: 청구서 '{claim_value}' / 위임장 '{poa_value}'", SUPPLEMENT)


def needs_delegation(claim_values):
    """청구서 예금주가 피보험자와 다르면 타인 위임이다."""
    holder, insured = claim_values.get("예금주", ""), claim_values.get("피보험자_성명", "")
    return bool(holder and insured and not _same(holder, insured))


def cross_check(claim_values, poa):
    """청구서 값과 위임장 값을 대조한다 (B02~B05)."""
    return _cross_check(claim_values, poa)


def _cross_check(claim_values, poa):
    c, p = claim_values, poa
    insured_poa = p.get("위임사항_피보험자") or p.get("피보험자명", "")
    claim_account = f"{c.get('은행명', '')} {c.get('계좌번호', '')}".strip()
    poa_account = f"{p.get('수임인_은행명', '')} {p.get('수임인_계좌번호', '')}".strip()
    claim_date = "-".join(c.get(k, "") for k in ["사고_년", "사고_월", "사고_일"]).strip("-")
    poa_date = "-".join(p.get(k, "") for k in ["사고_년", "사고_월", "사고_일"]).strip("-")
    return [
        _compare("B02", "위임받는 분·예금주", c.get("예금주", ""), p.get("수임인_성명", ""),
                 ["예금주", "수임인_성명"], _same(c.get("예금주", ""), p.get("수임인_성명", ""))),
        _compare("B03", "수령 계좌", claim_account if c.get("계좌번호") else "", poa_account if p.get("수임인_계좌번호") else "",
                 ["은행명", "계좌번호", "수임인_은행명", "수임인_계좌번호"],
                 _digits(c.get("계좌번호")) == _digits(p.get("수임인_계좌번호"))
                 and _same(c.get("은행명", ""), p.get("수임인_은행명", ""))),
        _compare("B04", "피보험자", c.get("피보험자_성명", ""), insured_poa,
                 ["피보험자_성명", "위임사항_피보험자"], _same(c.get("피보험자_성명", ""), insured_poa)),
        _compare("B05", "사고일", claim_date, poa_date, ["사고_년", "사고_월", "사고_일"],
                 _date_key(c.get("사고_년"), c.get("사고_월"), c.get("사고_일"))
                 == _date_key(p.get("사고_년"), p.get("사고_월"), p.get("사고_일"))),
    ]


def process_claim(claim, documents, engine="paddle", case_id=None, conn=None, extractors=None, classifier=None,
                  today=None, refs=None):
    """claim: claim_docs.required_documents가 받는 청구 정보. documents: [{"declared_type", "image"(없으면 None)}]"""
    extractors = extractors or _default_extractors()
    classifier = classifier or _default_classifier
    case_id = case_id or uuid.uuid4().hex[:12]

    processed, checks, merged_extracted = [], [], {}
    claim_form, poa = None, None
    for index, doc in enumerate(documents):
        entry = {"declared_type": doc["declared_type"], "classified_type": None, "form_code": None,
                 "engine": None, "engine_note": "", "extracted": {}, "values": {}, "rules": []}
        if doc.get("image") is not None:
            form_code, _ = classifier(doc["image"])
            entry["form_code"] = form_code
            entry["classified_type"] = _doc_type(form_code)
            if form_code in ("15", "16"):
                single = process_document(doc["image"], engine=engine, extractors=extractors,
                                          classifier=lambda image, code=form_code: (code, 0.0), today=today, refs=refs)
                entry.update({k: single[k] for k in ["engine", "engine_note", "extracted", "values", "rules"]})
                # 예금주 ≠ 피보험자(R11)는 건 단위에서 위임 서류 완비로 판단한다
                entry["rules"] = [r for r in entry["rules"] if r["rule"] != "R11"]
                claim_form = claim_form or entry
            elif form_code == "12":
                extracted, used, note = _extract(doc["image"], "12", engine, extractors)
                entry.update({"engine": used, "engine_note": note, "extracted": extracted,
                              "values": {k: v["value"] for k, v in extracted.items()}})
                poa = poa or entry
            if entry["classified_type"] and entry["classified_type"] != doc["declared_type"]:
                checks.append(_check("B06", "fail", [],
                                     f"'{doc['declared_type']}'(으)로 올린 서류가 '{entry['classified_type']}'(으)로 판별됐습니다",
                                     REVIEW))
        label = entry["classified_type"] or entry["declared_type"]
        for name, field in entry["extracted"].items():
            merged_extracted[f"{label}:{name}" if f"{label}:{name}" not in merged_extracted
                             else f"{label}#{index + 1}:{name}"] = field
        processed.append(entry)

    # 청구서 내용으로 청구 정보를 보강한다
    effective = dict(claim)
    if claim_form and claim_form["form_code"] == "16":
        holder, insured = claim_form["values"].get("예금주", ""), claim_form["values"].get("피보험자_성명", "")
        if needs_delegation(claim_form["values"]) and not claim["delegation"]:
            effective["delegation"] = True
            checks.append(_check("B01", "pass", ["예금주", "피보험자_성명"],
                                 f"예금주({holder})와 피보험자({insured})가 달라 위임 서류를 필요 서류에 추가했습니다",
                                 DOCUMENT))
        if poa:
            checks += _cross_check(claim_form["values"], poa["values"])
    if claim["type"] == "상해" and claim.get("injury_cause") == "발급불가" and claim_form:
        described = bool(claim_form["values"].get("사고경위"))
        checks.append(_check("B07", "pass" if described else "fail", ["사고경위"],
                             "사고확인서류를 발급받을 수 없는 경우 청구서 사고내용을 육하원칙에 따라 상세 기재해야 합니다",
                             SUPPLEMENT))

    requirements = required_documents(effective)
    submitted = {entry["classified_type"] or entry["declared_type"] for entry in processed}
    missing = check_completeness(requirements, submitted)
    completeness = [_check("D01", "fail", [], f"빠진 서류: {m['name']} — {m['reason']} (발급처: {m['issuer']})",
                           SUPPLEMENT) for m in missing]

    document_rules = [dict(r, message=f"[{e['classified_type'] or e['declared_type']}] {r['message']}")
                      for e in processed for r in e["rules"]]
    all_rules = completeness + checks + document_rules
    result = decide(all_rules, extracted=merged_extracted)

    bundle = {
        "case_id": case_id, "engine": engine, "claim": claim, "effective_claim": effective, "documents": processed,
        "requirements": requirements, "missing": missing, "checks": checks, **result,
        "status": "검토대기" if result["decision"] == REVIEW_DECISION else "처리완료",
    }
    if conn is not None:
        save_claim(conn, bundle)
        log_decision(conn, case_id, "AI", engine, result["decision"], result["reasons"])
    return bundle
