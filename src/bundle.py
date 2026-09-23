"""청구 건 단위 처리: 청구 정보 + 서류 묶음 → 구비서류 완비 판단 + 청구서·위임장 대조 + 건 결정.

- 이미지가 있는 서류(보험금청구서, 위임장)는 분류·추출한다. 청구서는 기존 검증 규칙(R01~R10)도 적용한다.
- 의료기관·관공서 서류는 공개 데이터에 이미지가 없어 고객이 고른 서류 종류만 받고 내용은 읽지 않는다.
- 청구서의 예금주가 피보험자와 다르면 위임 서류를 필요 목록에 자동으로 넣는다(단건 규칙 R11을 대신함).

건 단위 규칙
  D01 필요 서류 누락                         → 보완요청 (서류명·발급처 안내)
  B01 예금주 ≠ 피보험자 → 위임 서류 자동 추가  (안내)
  B01' 이름 확신도가 낮으면 자동 추가하지 않고 "위임 여부 확인 필요"  → 담당자검토
  B02 위임장 수임인 = 청구서 예금주            → 불일치 시 담당자검토
  B03 위임장 수령계좌·은행 = 청구서 계좌·은행   → 불일치 시 담당자검토
  B04 위임장 피보험자 = 청구서 피보험자         → 불일치 시 담당자검토
  B05 위임장 사고일 = 청구서 사고일            → 불일치 시 담당자검토
  B06 고객이 고른 서류 종류 ≠ 판별된 양식       → 담당자검토
  B07 상해 사고확인서류 발급불가인데 사고경위가 비어 있음 → 보완요청

상태: 자동접수 → 접수완료, 보완요청 → 보완대기(고객 재제출 대기), 담당자검토 → 검토대기.
보완대기 건에 고객이 서류를 더 내면(resubmit_claim) 같은 건에 붙여 다시 판단하고 회차별로 기록한다.

처리는 두 단계로 나눈다.
  1) read_documents: 이미지 서류를 분류·추출한다 (OCR은 여기서 한 번만).
  2) evaluate_claim: 저장된 값으로 규칙·대조·완비·결정을 계산한다.
담당자가 값을 고치거나 판단을 내리면(review_claim) OCR 없이 2)만 다시 돌린다.
"""
import re
import uuid
from datetime import datetime

from src.audit import get_claim, log_decision, log_edit, save_claim
from src.claim_docs import check_completeness, required_documents
from src.load_data import FORM_NAMES
from src.pipeline import _default_classifier, _default_extractors
from src.reference import normalize_name
from src.route import AUTO, CONFIDENCE_THRESHOLD, REVIEW_DECISION, SUPPLEMENT_DECISION, decide
from src.validate import DOCUMENT, REVIEW, SUPPLEMENT, validate

# 판별된 양식 코드 → 구비서류 규칙표의 서류 이름
FORM_DOC_TYPE = {"15": "보험금청구서", "16": "보험금청구서", "12": "위임장"}
EMPTY_REVIEW = {"delegation": None, "confirmed_mismatches": []}
STATUS_BY_DECISION = {AUTO: "접수완료", SUPPLEMENT_DECISION: "보완대기", REVIEW_DECISION: "검토대기"}
# 담당자 최종 처리 → 상태
STATUS_BY_FINAL = {"접수": "접수완료", "보완요청": "보완대기"}
# 다시 내면 이전 것을 대신하는 서류 (이미지로 읽는 양식)
REPLACEABLE = {"보험금청구서", "위임장"}


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
    # OCR로 읽은 두 서류의 불일치는 OCR 오류일 수 있다(일치하는 쌍에서도 24~58% 거짓 불일치, results/eval_bundle.csv).
    # 그래서 고객에게 바로 보완을 요청하지 않고 담당자가 원본을 확인한다.
    return _check(rule, "fail", fields,
                  f"{label} 불일치: 청구서 '{claim_value}' / 위임장 '{poa_value}' — 담당자 원본 확인 필요", REVIEW)


def needs_delegation(claim_values):
    """청구서 예금주가 피보험자와 다르면 타인 위임이다."""
    holder, insured = claim_values.get("예금주", ""), claim_values.get("피보험자_성명", "")
    return bool(holder and insured and not _same(holder, insured))


def cross_check(claim_values, poa):
    """청구서 값과 위임장 값을 대조한다 (B02~B05)."""
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


def read_documents(documents, engine="paddle", extractors=None, classifier=None):
    """1단계: 서류마다 양식을 판별하고, 청구서·위임장은 칸 값을 읽는다."""
    extractors = extractors or _default_extractors()
    classifier = classifier or _default_classifier
    entries = []
    for doc in documents:
        entry = {"declared_type": doc["declared_type"], "classified_type": None, "form_code": None,
                 "engine": None, "engine_note": "", "extracted": {}, "values": {}, "rules": [], "image_id": None}
        if doc.get("image") is not None:
            # 원본 이미지를 담당자 화면에서 다시 보여주기 위한 ID (서류 순서가 바뀌어도 안 섞이게)
            entry["image_id"] = uuid.uuid4().hex[:12]
            form_code, _ = classifier(doc["image"])
            entry["form_code"] = form_code
            entry["classified_type"] = _doc_type(form_code)
            if form_code in ("12", "15", "16"):
                extracted, used, note = _extract(doc["image"], form_code, engine, extractors)
                entry.update({"engine": used, "engine_note": note, "extracted": extracted,
                              "values": {k: v["value"] for k, v in extracted.items()}})
        entries.append(entry)
    return entries


def _label(entry):
    return entry["classified_type"] or entry["declared_type"]


def _first(entries, codes):
    return next((e for e in entries if e["form_code"] in codes), None)


def _delegation_check(claim, claim_form, review, effective, checks):
    """위임 필요 여부: 담당자 판단이 있으면 그것을, 없으면 청구서 값(이름 확신도 조건부)으로 정한다."""
    if review["delegation"] is not None:
        effective["delegation"] = review["delegation"]
        checks.append(_check("B01", "pass", ["예금주", "피보험자_성명"],
                             f"담당자 판단: 위임 {'필요' if review['delegation'] else '불필요'}", DOCUMENT))
        return
    if not claim_form or claim_form["form_code"] != "16":
        return
    if not needs_delegation(claim_form["values"]) or claim["delegation"]:
        return
    holder, insured = claim_form["values"].get("예금주", ""), claim_form["values"].get("피보험자_성명", "")
    scores = [claim_form["extracted"].get(f, {}).get("score", 0) for f in ["예금주", "피보험자_성명"]]
    if min(scores) >= CONFIDENCE_THRESHOLD:
        effective["delegation"] = True
        checks.append(_check("B01", "pass", ["예금주", "피보험자_성명"],
                             f"예금주({holder})와 피보험자({insured})가 달라 위임 서류를 필요 서류에 추가했습니다", DOCUMENT))
    else:
        # 이름을 잘못 읽어 달라 보일 수 있다 → 고객에게 불필요한 위임 서류를 요구하지 않도록 담당자가 확인
        checks.append(_check("B01", "unknown", ["예금주", "피보험자_성명"],
                             f"예금주({holder})와 피보험자({insured})가 달라 보이지만 이름 확신도가 낮아 위임 여부 확인 필요",
                             REVIEW))


def evaluate_claim(claim, entries, case_id, engine="paddle", today=None, refs=None, review=None):
    """2단계: 저장된 서류 값으로 건 단위 판단을 계산한다.

    review(담당자 판단): {"delegation": None/True/False, "confirmed_mismatches": [규칙 ID]}
    """
    review = review or dict(EMPTY_REVIEW)
    checks, merged_extracted = [], {}
    for index, entry in enumerate(entries):
        if entry["form_code"] in ("15", "16"):
            # 청구서 단건 규칙. 예금주 ≠ 피보험자(R11)는 건 단위에서 위임 서류 완비로 판단한다
            entry["rules"] = [r for r in validate(entry["form_code"], entry["values"], today=today, refs=refs)
                              if r["rule"] != "R11"]
        if entry["classified_type"] and entry["classified_type"] != entry["declared_type"]:
            checks.append(_check("B06", "fail", [],
                                 f"'{entry['declared_type']}'(으)로 올린 서류가 '{entry['classified_type']}'(으)로 판별됐습니다",
                                 REVIEW))
        for name, field in entry["extracted"].items():
            key = f"{_label(entry)}:{name}"
            merged_extracted[key if key not in merged_extracted else f"{_label(entry)}#{index + 1}:{name}"] = field

    claim_form, poa = _first(entries, ("15", "16")), _first(entries, ("12",))
    effective = dict(claim)
    _delegation_check(claim, claim_form, review, effective, checks)
    if claim_form and claim_form["form_code"] == "16" and poa:
        for check in cross_check(claim_form["values"], poa["values"]):
            if check["status"] == "fail" and check["rule"] in review["confirmed_mismatches"]:
                # 담당자가 원본으로 실제 불일치를 확인했으면 고객에게 보완을 요청한다
                check = dict(check, action=SUPPLEMENT,
                             message=check["message"].replace(" — 담당자 원본 확인 필요", " — 서류를 다시 확인해 주세요"))
            checks.append(check)
    if claim["type"] == "상해" and claim.get("injury_cause") == "발급불가" and claim_form:
        described = bool(claim_form["values"].get("사고경위"))
        checks.append(_check("B07", "pass" if described else "fail", ["사고경위"],
                             "사고확인서류를 발급받을 수 없는 경우 청구서 사고내용을 육하원칙에 따라 상세 기재해야 합니다",
                             SUPPLEMENT))

    requirements = required_documents(effective)
    missing = check_completeness(requirements, {_label(e) for e in entries})
    completeness = [_check("D01", "fail", [], f"빠진 서류: {m['name']} — {m['reason']} (발급처: {m['issuer']})",
                           SUPPLEMENT) for m in missing]
    document_rules = [dict(r, message=f"[{_label(e)}] {r['message']}") for e in entries for r in e["rules"]]
    result = decide(completeness + checks + document_rules, extracted=merged_extracted)
    return {
        "case_id": case_id, "engine": engine, "claim": claim, "effective_claim": effective, "documents": entries,
        "requirements": requirements, "missing": missing, "checks": checks, "review": review, **result,
        "status": STATUS_BY_DECISION[result["decision"]],
    }


def _round(number, submitted, bundle, previous_missing=None):
    """접수 회차 기록: 이번에 낸 서류, 결정, 해결된 누락 서류, 아직 빠진 서류."""
    still = [m["name"] for m in bundle["missing"]]
    return {
        "round": number, "at": datetime.now().isoformat(timespec="seconds"), "submitted": submitted,
        "decision": bundle["decision"],
        "resolved": [name for name in (previous_missing or []) if name not in still],
        "still_missing": still,
    }


def process_claim(claim, documents, engine="paddle", case_id=None, conn=None, extractors=None, classifier=None,
                  today=None, refs=None):
    """claim: claim_docs.required_documents가 받는 청구 정보. documents: [{"declared_type", "image"(없으면 None)}]"""
    case_id = case_id or uuid.uuid4().hex[:12]
    entries = read_documents(documents, engine, extractors, classifier)
    bundle = evaluate_claim(claim, entries, case_id, engine, today, refs)
    bundle["rounds"] = [_round(1, [_label(e) for e in entries], bundle)]
    if conn is not None:
        save_claim(conn, bundle)
        log_decision(conn, case_id, "AI", engine, bundle["decision"], bundle["reasons"])
    return bundle


def review_claim(conn, case_id, editor, edits=None, confirmed_fields=None, confirmed_mismatches=None, delegation=None,
                 today=None, refs=None):
    """담당자 검토를 반영하고 OCR 없이 다시 판단한다.

    edits: {서류 순번: {칸: 새 값}} — 고친 칸은 이력을 남기고 확신도 1.0
    confirmed_fields: {서류 순번: [칸]} — 값은 그대로 두고 원본과 맞다고 확인한 칸 (확신도 1.0)
    confirmed_mismatches: 원본으로 실제 불일치를 확인한 대조 규칙 ID (고객 보완요청으로 바뀜)
    delegation: 위임 필요 여부에 대한 담당자 판단 (None이면 이전 판단 유지, 처음이면 청구서 값으로 자동 판단)
    """
    bundle = get_claim(conn, case_id)
    entries = bundle["documents"]
    for index, changes in (edits or {}).items():
        entry = entries[int(index)]
        for field, new in changes.items():
            old = entry["values"].get(field, "")
            if new != old:
                log_edit(conn, case_id, f"{_label(entry)}:{field}", old, new, editor)
            entry["values"][field] = new
            entry["extracted"][field] = {"value": new, "raw": entry["extracted"].get(field, {}).get("raw", ""),
                                         "score": 1.0}
    for index, fields in (confirmed_fields or {}).items():
        entry = entries[int(index)]
        for field in fields:
            if field in entry["extracted"]:
                entry["extracted"][field]["score"] = 1.0
    review = dict(bundle.get("review") or EMPTY_REVIEW)
    review["confirmed_mismatches"] = sorted(set(review["confirmed_mismatches"]) | set(confirmed_mismatches or []))
    if delegation is not None:
        review["delegation"] = delegation
    updated = evaluate_claim(bundle["claim"], entries, case_id, bundle["engine"], today, refs, review)
    updated["created_at"] = bundle.get("created_at")
    updated["rounds"] = bundle.get("rounds", [])
    save_claim(conn, updated)
    log_decision(conn, case_id, f"{editor}(검토 후 재판단)", bundle["engine"], updated["decision"], updated["reasons"])
    return updated


def finalize_claim(conn, case_id, editor, final_decision):
    """담당자가 최종 처리(예: '접수', '보완요청')를 확정하고 건을 닫는다."""
    bundle = get_claim(conn, case_id)
    bundle["status"] = STATUS_BY_FINAL[final_decision]
    bundle["final_decision"] = final_decision
    save_claim(conn, bundle)
    log_decision(conn, case_id, editor, bundle["engine"], final_decision, ["담당자 최종 확인"])
    return bundle


def resubmit_claim(conn, case_id, documents, engine=None, extractors=None, classifier=None, today=None, refs=None):
    """보완대기 건에 고객이 추가로 낸 서류를 붙여 다시 판단한다.

    새로 낸 청구서·위임장은 이전 것을 대신한다(고쳐서 다시 낸 경우). 이때 이전 서류 값으로 한
    담당자의 불일치 확정은 무효가 된다. 위임 여부 판단은 그대로 둔다.
    """
    bundle = get_claim(conn, case_id)
    if bundle["status"] != "보완대기":
        raise ValueError(f"보완대기 상태인 건만 재제출할 수 있습니다 (현재: {bundle['status']})")
    engine = engine or bundle["engine"]
    new_entries = read_documents(documents, engine, extractors, classifier)
    replaced = {_label(e) for e in new_entries if _label(e) in REPLACEABLE}
    entries = [e for e in bundle["documents"] if _label(e) not in replaced] + new_entries
    review = dict(bundle.get("review") or EMPTY_REVIEW)
    if replaced:
        review["confirmed_mismatches"] = []
    updated = evaluate_claim(bundle["claim"], entries, case_id, bundle["engine"], today, refs, review)
    previous_missing = [m["name"] for m in bundle["missing"]]
    updated["created_at"] = bundle.get("created_at")
    updated["rounds"] = bundle.get("rounds", []) + [
        _round(len(bundle.get("rounds", [])) + 1, [_label(e) for e in new_entries], updated, previous_missing)]
    save_claim(conn, updated)
    log_decision(conn, case_id, "고객 재제출", engine, updated["decision"], updated["reasons"])
    return updated
