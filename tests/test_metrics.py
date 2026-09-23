from src.metrics import cer, edit_distance, is_exact, normalize


def test_normalize_removes_all_spaces():
    assert normalize(" 의료법인 발해 병원 ") == "의료법인발해병원"


def test_is_exact_ignores_spaces():
    assert is_exact("자 전거 사고", "자전거사고")
    assert not is_exact("마키터", "마케터")


def test_edit_distance():
    assert edit_distance("마키터", "마케터") == 1
    assert edit_distance("", "abc") == 3
    assert edit_distance("kitten", "sitting") == 3


def test_cer_is_distance_over_truth_length():
    assert cer("마키터", "마케터") == 1 / 3
    assert cer("", "") == 0.0
    assert cer("잡음", "") == 1.0


def test_amount_fields_compare_digits_only():
    assert is_exact("6,041,881", "6,041,881원", field="타사가입금액")
    assert is_exact("5.986만원", "5,986만원", field="가입금액")
    assert not is_exact("2,463만원", "7,463만원", field="가입금액")
    # 다른 칸은 그대로 엄격하게 비교
    assert not is_exact("6,041,881", "6,041,881원")


def test_email_is_case_insensitive():
    assert is_exact("6iV40f@xaod.or.kr", "6iv40f@xaod.or.kr", field="이메일")
    assert cer("ABC@X.KR", "abc@x.kr", field="이메일") == 0.0
