"""기준 데이터 조회: 질병코드(KCD-9), 직업코드(KSCO 8차), 은행 목록, 도로명주소.

원본 파일(엑셀·PDF·텍스트)은 읽는 데 시간이 걸리므로 처음 한 번만 읽어
data/processed/reference_cache/에 JSON으로 저장해 두고 재사용한다.
"""
import difflib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from functools import lru_cache

from src.load_data import PROJECT_ROOT
from src.metrics import edit_distance

REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "reference_cache"
JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
SYNONYMS_PATH = PROJECT_ROOT / "config" / "diagnosis_synonyms.json"
# 이 값 이상 비슷하면 '유사 후보'로 본다 (0~1, difflib 기준)
SIMILARITY_CUTOFF = 0.8
# 자모 단위 비교: 이 거리 이하는 후보로 보여 주고, 거리 1이면서 후보가 하나뿐이면 OCR 오류로 보고 보정한다.
# 검증 청구서의 진단명에서 거리 1·유일 후보 보정은 23건 중 22건이 정답이었다 (틀린 1건은 정답도 KCD에 없는 이름).
JAMO_CANDIDATE_DISTANCE = 3
JAMO_CORRECT_DISTANCE = 1
CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
NO_MATCH = {"match": "none", "code": None, "name": None, "candidates": []}


def normalize_name(text):
    """전각 문자(Ｋ, Ｂ 등)를 보통 문자로 바꾸고 공백을 모두 없앤다."""
    return "".join(unicodedata.normalize("NFKC", str(text)).split())


@lru_cache(maxsize=200_000)
def to_jamo(text):
    """한글 음절을 자모로 푼다. '염'과 '영'처럼 받침 하나만 다른 OCR 오류가 거리 1이 된다."""
    out = []
    for ch in text:
        index = ord(ch) - 0xAC00
        if 0 <= index < 11172:
            out += [CHOSEONG[index // 588], JUNGSEONG[index % 588 // 28]]
            if index % 28:
                out.append(JONGSEONG[index % 28])
        else:
            out.append(ch)
    return "".join(out)


def load_env(path=PROJECT_ROOT / ".env"):
    """.env 파일의 KEY=VALUE 줄을 dict로 읽는다. 파일이 없으면 빈 dict."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    return env


def _cached(file_name, builder):
    path = CACHE_DIR / file_name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = builder()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _build_kcd():
    import openpyxl
    workbook = openpyxl.load_workbook(REFERENCE_DIR / "KCD-9 DB masterfile.xlsx", read_only=True)
    table = {}
    # 열: 0 표제어, 2 질병분류코드, 5 한글명칭, 7 최하위코드 여부 (4행부터 데이터)
    for row in workbook["KCD-9 DB Masterfile"].iter_rows(min_row=4, values_only=True):
        code, korean_name = row[2], row[5]
        if code and korean_name:
            table.setdefault(normalize_name(korean_name), [str(code).strip(), str(korean_name).strip()])
    return table


def _build_ksco():
    from pypdf import PdfReader
    pdf_path = next(REFERENCE_DIR.glob("제8차 한국표준직업분류 분류항목표*.pdf"))
    text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    table = {}
    # 세세분류 줄: "   12121 총무 및 인사 관리자 General Affairs ..." → 5자리 코드 + 영문 앞까지의 한글명
    for match in re.finditer(r"(?m)^\s*(\d{5})\s*([^A-Za-z\n]+)", text):
        name = match.group(2).strip()
        table.setdefault(normalize_name(name), [match.group(1), name])
    return table


def _build_banks():
    raw = (REFERENCE_DIR / "금융회사코드.text").read_bytes().decode("cp949", errors="replace")
    banks = {}
    # 한 줄 = 점포 하나: "0010003|한국　　|본부총괄|..." 앞 3자리가 금융회사 코드
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) > 2:
            banks.setdefault(parts[0][:3], normalize_name(parts[1]))
    return banks


@lru_cache(maxsize=None)
def kcd_table():
    return _cached("kcd9.json", _build_kcd)


@lru_cache(maxsize=None)
def ksco_table():
    return _cached("ksco8.json", _build_ksco)


@lru_cache(maxsize=None)
def bank_table():
    return _cached("banks.json", _build_banks)


def _jamo_neighbors(key, table):
    """자모 거리가 가까운 기준표 이름 [(거리, 키)] (가까운 순, 최대 3개)."""
    query = to_jamo(key)
    scored = []
    for other in table:
        if abs(len(other) - len(key)) > 1:
            continue
        jamo = to_jamo(other)
        if abs(len(jamo) - len(query)) > JAMO_CANDIDATE_DISTANCE:
            continue
        distance = edit_distance(query, jamo)
        if distance <= JAMO_CANDIDATE_DISTANCE:
            scored.append((distance, other))
    return sorted(scored)[:3]


def match_name(query, table, allow_contains=False, synonyms=None):
    """이름을 기준표에서 찾는다.

    정확 일치 → 흔히 쓰는 이름 사전 → (허용 시) 부분 일치 → 자모 한 개 차이 보정 → 유사 후보 순서.
    """
    key = normalize_name(query)
    if not key:
        return dict(NO_MATCH)
    if key in table:
        code, name = table[key]
        return {"match": "exact", "code": code, "name": name, "candidates": []}
    target = (synonyms or {}).get(key)
    if target in table:
        code, name = table[target]
        return {"match": "synonym", "code": code, "name": name, "candidates": []}
    if allow_contains:
        hits = [k for k in table if key in k]
        if hits:
            code, name = table[hits[0]]
            return {"match": "contains", "code": code, "name": name, "candidates": [table[h][1] for h in hits[:5]]}
    neighbors = _jamo_neighbors(key, table)
    if neighbors:
        distance, best = neighbors[0]
        unique = len(neighbors) == 1 or neighbors[1][0] > distance
        # 한 글자짜리는 다른 이름으로 바뀌기 쉬워 보정하지 않는다
        kind = "corrected" if distance <= JAMO_CORRECT_DISTANCE and unique and len(key) >= 2 else "similar"
        code, name = table[best]
        return {"match": kind, "code": code, "name": name, "candidates": [table[k][1] for _, k in neighbors]}
    # 길이가 비슷한 이름만 비교해 속도를 높인다
    nearby = [k for k in table if abs(len(k) - len(key)) <= 2]
    close = difflib.get_close_matches(key, nearby, n=3, cutoff=SIMILARITY_CUTOFF)
    if close:
        code, name = table[close[0]]
        return {"match": "similar", "code": code, "name": name, "candidates": [table[c][1] for c in close]}
    return dict(NO_MATCH)


@lru_cache(maxsize=None)
def diagnosis_synonyms():
    """{정규화한 흔히 쓰는 이름: 정규화한 KCD 공식 이름}"""
    raw = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))
    return {normalize_name(k): normalize_name(v) for k, v in raw.items() if not k.startswith("_")}


def lookup_diagnosis(name):
    return match_name(name, kcd_table(), synonyms=diagnosis_synonyms())


def lookup_job(name):
    return match_name(name, ksco_table(), allow_contains=True)


def is_known_bank(name, banks=None):
    """은행명이 금융회사 목록에 있는지.

    '신한은행'과 '신한', '국민은행'과 공식 이름 'KB국민'은 같은 은행으로 본다.
    """
    names = {normalize_name(n) for n in (banks or bank_table()).values()}
    core = normalize_name(name).removesuffix("은행")
    if len(core) < 2:
        return False
    # 공식 이름이 입력으로 끝나면 같은 은행 (KB국민 ← 국민, NH농협 ← 농협). 중간에 든 것(새마을금고 ← 마을)은 제외
    return any(n.removesuffix("은행").endswith(core) for n in names)


def _fetch_juso(address, key):
    if not key:
        raise RuntimeError("도로명주소 승인키가 없습니다")
    query = urllib.parse.urlencode({
        "confmKey": key, "currentPage": 1, "countPerPage": 1, "keyword": address, "resultType": "json",
    })
    with urllib.request.urlopen(f"{JUSO_URL}?{query}", timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    common = data["results"]["common"]
    if common["errorCode"] != "0":
        # 승인키 만료(90일) 등은 여기서 오류로 처리된다
        raise RuntimeError(common["errorMessage"])
    return data["results"]["juso"] or []


def check_address(address, key=None, fetch=None, cache_path=CACHE_DIR / "juso_cache.json"):
    """주소가 실제로 있는지 도로명주소 API로 확인한다. 조회 실패는 'unavailable'(캐시하지 않음)."""
    address = " ".join(str(address).split())
    if not address:
        return {"status": "not_found", "road_addr": None}
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if address in cache:
        return cache[address]
    try:
        found = (fetch or _fetch_juso)(address, key if key is not None else load_env().get("API1"))
    except Exception:
        return {"status": "unavailable", "road_addr": None}
    if found:
        result = {"status": "found", "road_addr": found[0]["roadAddr"]}
    else:
        result = {"status": "not_found", "road_addr": None}
    cache[address] = result
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return result
