"""접수 검증 규칙 R01~R11.

청구서 칸 값(dict)을 받아 규칙마다 결과를 돌려준다. 결과 하나는
{"rule", "status": pass/fail/unknown, "fields", "message", "action", "detail"} 모양이다.
기준 데이터 조회(질병코드·직업·은행·주소)는 refs로 바꿔 끼울 수 있어 테스트 때 파일·네트워크가 필요 없다.
"""
import re
from datetime import date

from src import reference

SUPPLEMENT = "보완요청"   # 고객이 고쳐서 다시 내야 함
REVIEW = "담당자검토"      # 사람이 판단해야 함
DOCUMENT = "추가서류"      # 서류를 더 받아야 함

REQUIRED_FIELDS = {
    "16": ["피보험자_성명", "주민번호", "직업", "주소_시도", "연락처", "사고_년", "사고_월", "사고_일",
           "진단명", "계좌번호", "은행명", "예금주", "작성_년", "작성_월", "작성_일", "청구권자"],
    "15": ["보험종목", "증권번호", "계약자", "사고일자", "사고원인", "사고경위", "청구_년", "청구_월",
           "청구_일", "청구인_성명", "주소_시도", "연락처"],
}
ADDRESS_FIELDS = ["주소_시도", "주소_시군구", "주소_도로명", "주소_번지"]
CLAIM_LIMIT_YEARS = 3  # 보험금 청구권 소멸시효 (상법 제662조)

DEFAULT_REFS = {
    "diagnosis": reference.lookup_diagnosis,
    "job": reference.lookup_job,
    "bank": reference.is_known_bank,
    "address": reference.check_address,
}

PHONE_PATTERN = re.compile(r"0\d{1,2}-?\d{3,4}-?\d{4}")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# 주민번호 뒤 첫 자리 → 태어난 세기
RRN_CENTURY = {"1": 1900, "2": 1900, "5": 1900, "6": 1900, "3": 2000, "4": 2000, "7": 2000, "8": 2000}


def _result(rule, passed, fields, message, action, detail=None, status=None):
    return {
        "rule": rule,
        "status": status or ("pass" if passed else "fail"),
        "fields": fields,
        "message": "" if passed and not status else message,
        "action": action,
        "detail": detail or {},
    }


def _parse_date(year, month, day):
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def _add_years(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 2월 29일
        return day.replace(year=day.year + years, day=28)


def _dates(form_code, v):
    """{이름: (칸 목록, 적힌 글자, 날짜 또는 None)}"""
    if form_code == "16":
        accident = ["사고_년", "사고_월", "사고_일"]
        written = ["작성_년", "작성_월", "작성_일"]
        accident_date = _parse_date(*(v.get(f) for f in accident))
        written_date = _parse_date(*(v.get(f) for f in written))
    else:
        accident = ["사고일자"]
        written = ["청구_년", "청구_월", "청구_일"]
        parts = re.split(r"[.\-/]", v.get("사고일자", ""))
        accident_date = _parse_date(*parts) if len(parts) == 3 else None
        # 구양식은 "20__년"의 뒤 두 자리만 손으로 쓴다
        year = v.get("청구_년", "")
        written_date = _parse_date(2000 + int(year) if year.isdigit() else None, v.get("청구_월"), v.get("청구_일"))
    return {
        "사고일": (accident, "-".join(v.get(f, "") for f in accident), accident_date),
        "작성일": (written, "-".join(v.get(f, "") for f in written), written_date),
    }


def _valid_date(day, today):
    return day is not None and 1900 <= day.year <= today.year


def _check_rrn(text):
    digits = text.replace("-", "")
    if not re.fullmatch(r"\d{13}", digits):
        return "주민번호가 앞 6자리-뒤 7자리 형식이 아닙니다"
    century = RRN_CENTURY.get(digits[6])
    if century is None:
        return "주민번호 뒤 첫 자리(성별)가 1~8이 아닙니다"
    if _parse_date(century + int(digits[:2]), digits[2:4], digits[4:6]) is None:
        return "주민번호의 생년월일이 실제 날짜가 아닙니다"
    return None


def _match_rule(rule, field, value, lookup, label):
    """질병코드·직업코드처럼 기준표에서 이름을 찾는 규칙. 정확 일치만 통과."""
    found = lookup(value)
    if found["match"] == "exact":
        return _result(rule, True, [field], "", REVIEW, detail={"code": found["code"], "name": found["name"]})
    if found["candidates"]:
        message = f"{label} '{value}'과(와) 정확히 일치하는 코드가 없습니다. 후보: {', '.join(found['candidates'])}"
    else:
        message = f"{label} '{value}'에 해당하는 코드를 찾지 못했습니다"
    return _result(rule, False, [field], message, REVIEW, detail=found)


def validate(form_code, values, today=None, refs=None):
    today = today or date.today()
    refs = refs or DEFAULT_REFS
    v = {name: str(value).strip() for name, value in values.items() if value is not None}
    results = []

    # R01 필수 칸
    missing = [f for f in REQUIRED_FIELDS[form_code] if not v.get(f)]
    results.append(_result("R01", not missing, missing, f"필수 항목이 비어 있습니다: {', '.join(missing)}", SUPPLEMENT))

    # R02 날짜 실재 / R03 날짜 순서 / R04 소멸시효
    dates = _dates(form_code, v)
    bad = [(name, fields, text) for name, (fields, text, day) in dates.items()
           if text.strip("-") and not _valid_date(day, today)]
    written_any = any(text.strip("-") for _, text, _ in dates.values())
    if written_any:
        results.append(_result(
            "R02", not bad, [f for _, fields, _ in bad for f in fields],
            "; ".join(f"{name} '{text}'이(가) 올바른 날짜가 아닙니다" for name, _, text in bad), SUPPLEMENT))
    accident_fields, _, accident = dates["사고일"]
    written_fields, _, written = dates["작성일"]
    accident_ok, written_ok = _valid_date(accident, today), _valid_date(written, today)
    if accident_ok and written_ok:
        in_order = accident <= written <= today
        results.append(_result(
            "R03", in_order, accident_fields + written_fields,
            f"날짜 순서가 맞지 않습니다 (사고일 {accident}, 작성일 {written}, 오늘 {today})", SUPPLEMENT))
    if accident_ok:
        base = written if written_ok else today
        within = base <= _add_years(accident, CLAIM_LIMIT_YEARS)
        results.append(_result(
            "R04", within, accident_fields,
            f"사고일 {accident}로부터 {CLAIM_LIMIT_YEARS}년이 지나 청구권 소멸시효(상법 제662조) 확인이 필요합니다", REVIEW))

    # R05 주민번호 (신양식)
    if form_code == "16" and v.get("주민번호"):
        problem = _check_rrn(v["주민번호"])
        results.append(_result("R05", problem is None, ["주민번호"], problem or "", SUPPLEMENT))

    # R06 연락처·이메일 형식
    format_fields = [f for f, pattern in [("연락처", PHONE_PATTERN), ("이메일", EMAIL_PATTERN)] if v.get(f)]
    if format_fields:
        wrong = [f for f in format_fields
                 if not (PHONE_PATTERN if f == "연락처" else EMAIL_PATTERN).fullmatch(v[f])]
        results.append(_result("R06", not wrong, wrong, f"형식이 올바르지 않습니다: {', '.join(wrong)}", SUPPLEMENT))

    # R07 주소 실재
    if v.get("주소_시도"):
        address = " ".join(v.get(f, "") for f in ADDRESS_FIELDS)
        found = refs["address"](address)
        if found["status"] == "unavailable":
            results.append(_result("R07", False, ADDRESS_FIELDS, "주소 조회 서비스에 연결하지 못해 확인하지 못했습니다",
                                   REVIEW, status="unknown"))
        else:
            results.append(_result("R07", found["status"] == "found", ADDRESS_FIELDS,
                                   f"주소 '{' '.join(address.split())}'을(를) 찾을 수 없습니다", SUPPLEMENT,
                                   detail={"road_addr": found["road_addr"]}))

    if form_code == "16":
        # R08 진단명 → 질병코드, R09 직업 → 직업코드
        if v.get("진단명"):
            results.append(_match_rule("R08", "진단명", v["진단명"], refs["diagnosis"], "진단명"))
        if v.get("직업"):
            results.append(_match_rule("R09", "직업", v["직업"], refs["job"], "직업"))

        # R10 은행명·계좌번호
        if v.get("은행명") or v.get("계좌번호"):
            wrong, reasons = [], []
            if v.get("은행명") and not refs["bank"](v["은행명"]):
                wrong.append("은행명")
                reasons.append(f"'{v['은행명']}'은(는) 등록된 금융회사가 아닙니다")
            digits = re.sub(r"\D", "", v.get("계좌번호", ""))
            if v.get("계좌번호") and not 10 <= len(digits) <= 14:
                wrong.append("계좌번호")
                reasons.append(f"계좌번호 숫자가 {len(digits)}자리입니다 (10~14자리)")
            results.append(_result("R10", not wrong, wrong, "; ".join(reasons), SUPPLEMENT))

        # R11 예금주 ≠ 피보험자 → 위임장·인감증명서
        holder, insured = v.get("예금주"), v.get("피보험자_성명")
        if holder and insured:
            same = reference.normalize_name(holder) == reference.normalize_name(insured)
            results.append(_result(
                "R11", same, ["예금주", "피보험자_성명"],
                f"예금주({holder})와 피보험자({insured})가 달라 위임장과 인감증명서가 필요합니다", DOCUMENT))

    return results
