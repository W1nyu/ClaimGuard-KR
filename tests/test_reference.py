import json

from src.reference import check_address, is_known_bank, match_name, normalize_name

TABLE = {
    "멀미": ["T75.3", "멀미"],
    "늑골골절": ["S22.3", "늑골 골절"],
    "한식조리사": ["41121", "한식 조리사"],
    "양식조리사": ["41122", "양식 조리사"],
}


def test_normalize_name_handles_fullwidth_and_spaces():
    assert normalize_name("ＫＢ국민 ") == "KB국민"
    assert normalize_name("늑골 골절") == "늑골골절"


def test_exact_match_ignores_spaces():
    result = match_name("늑골 골절", TABLE)
    assert result["match"] == "exact"
    assert result["code"] == "S22.3"


def test_contains_match_only_when_allowed():
    assert match_name("조리사", TABLE)["match"] == "none"
    result = match_name("조리사", TABLE, allow_contains=True)
    assert result["match"] == "contains"
    assert result["candidates"] == ["한식 조리사", "양식 조리사"]


def test_similar_match_gives_candidates():
    # 한 글자가 더 붙은 경우: 유사도 2×4/9 ≈ 0.89 ≥ 0.8
    result = match_name("늑골골절증", TABLE)
    assert result["match"] == "similar"
    assert result["code"] == "S22.3"


def test_no_match_and_empty():
    assert match_name("검투사", TABLE)["match"] == "none"
    assert match_name("", TABLE) == {"match": "none", "code": None, "name": None, "candidates": []}


def test_known_bank_allows_eunhaeng_suffix():
    banks = {"004": "KB국민", "020": "우리은행", "088": "신한"}
    assert is_known_bank("신한은행", banks)
    assert is_known_bank("우리", banks)
    assert is_known_bank("ＫＢ국민", banks)
    # 흔히 쓰는 이름 '국민은행'은 공식 목록의 'KB국민'과 같은 은행
    assert is_known_bank("국민은행", banks)
    assert not is_known_bank("무궁", banks)
    assert not is_known_bank("은행", banks)


def test_bank_name_inside_another_name_is_not_a_match():
    # '마을'은 '새마을금고' 안에 들어 있지만 다른 이름이다
    assert not is_known_bank("마을", {"045": "새마을금고"})
    assert is_known_bank("농협", {"011": "NH농협은행"})


def test_check_address_found_and_cached(tmp_path):
    cache = tmp_path / "juso.json"
    calls = []

    def fake_fetch(address, key):
        calls.append(address)
        return [{"roadAddr": "서울특별시 중구 세종대로 110 (태평로1가)"}]

    first = check_address("서울특별시  중구 세종대로 110", key="k", fetch=fake_fetch, cache_path=cache)
    second = check_address("서울특별시 중구 세종대로 110", key="k", fetch=fake_fetch, cache_path=cache)
    assert first == second == {"status": "found", "road_addr": "서울특별시 중구 세종대로 110 (태평로1가)"}
    assert calls == ["서울특별시 중구 세종대로 110"]
    assert "서울특별시 중구 세종대로 110" in json.loads(cache.read_text(encoding="utf-8"))


def test_check_address_not_found(tmp_path):
    result = check_address("세종특별자치시 김천시 장동 186", key="k", fetch=lambda a, k: [], cache_path=tmp_path / "c.json")
    assert result == {"status": "not_found", "road_addr": None}


def test_check_address_failure_is_unavailable_and_not_cached(tmp_path):
    cache = tmp_path / "c.json"

    def broken(address, key):
        raise TimeoutError("네트워크 오류")

    assert check_address("서울 중구", key="k", fetch=broken, cache_path=cache)["status"] == "unavailable"
    assert not cache.exists()
