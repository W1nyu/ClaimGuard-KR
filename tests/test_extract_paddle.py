from PIL import Image

from src.extract_paddle import clean_value, extract_fields
from src.form_templates import load_form_fields


def test_clean_value_fixes_digit_lookalikes():
    assert clean_value("사고_월", "(|") == "11"
    assert clean_value("사고_일", "1|2") == "112"
    assert clean_value("사고_시", "6.") == "6"
    assert clean_value("작성_년", "O8S7") == "0857"


def test_clean_value_keeps_allowed_symbols():
    assert clean_value("주민번호", "598096-2264335") == "598096-2264335"
    assert clean_value("사고일자", "7907.2.20") == "7907.2.20"
    assert clean_value("사고시각", "11:52") == "11:52"


def test_clean_value_leaves_text_fields_alone():
    assert clean_value("직업", " 마키터 ") == "마키터"
    assert clean_value("이메일", "8mrih9@aazc.or.kr") == "8mrih9@aazc.or.kr"


class FakeRecognizer:
    """PaddleOCR 대신 쓰는 가짜 인식기: 잘린 이미지 수만큼 같은 결과를 돌려준다."""

    def __init__(self):
        self.crop_count = 0

    def predict(self, crops, batch_size=8):
        self.crop_count = len(crops)
        return [{"rec_text": "1|", "rec_score": 0.5} for _ in crops]


def test_extract_fields_returns_every_field_with_score():
    image = Image.new("RGB", (2480, 3508), "white")
    fake = FakeRecognizer()
    result = extract_fields(image, "16", recognizer=fake)
    assert fake.crop_count == len(load_form_fields("16"))
    assert set(result) == set(load_form_fields("16"))
    assert result["사고_월"] == {"value": "11", "raw": "1|", "score": 0.5}
    assert result["직업"]["value"] == "1|"
