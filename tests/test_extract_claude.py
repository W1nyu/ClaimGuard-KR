import pytest
from PIL import Image

from src.extract_claude import (
    CERTAIN_SCORE, UNCERTAIN_SCORE, build_prompt, extract_fields_cli, parse_response, prepare_image,
)
from src.form_templates import load_form_fields


def test_prompt_lists_every_field_and_forbids_correction():
    for code in ["12", "15", "16"]:
        prompt = build_prompt(code, "C:/tmp/a.png")
        for field in load_form_fields(code):
            assert field in prompt
    assert "C:/tmp/a.png" in prompt
    assert "고치지" in prompt


def test_prepare_image_crops_and_shrinks():
    image = Image.new("RGB", (2480, 3508), "white")
    small = prepare_image(image, "16")
    assert max(small.size) == 1600


def test_parse_response_reads_code_block_and_uncertain_fields():
    text = """네, 결과입니다.
```json
{"values": {"피보험자_성명": "서동우", "사고_월": "(|", "직업": "마케터"}, "uncertain": ["직업"]}
```"""
    result = parse_response(text, "16")
    assert set(result) == set(load_form_fields("16"))
    assert result["피보험자_성명"] == {"value": "서동우", "raw": "서동우", "score": CERTAIN_SCORE}
    assert result["직업"]["score"] == UNCERTAIN_SCORE
    # 숫자 칸은 엔진 A와 같은 보정을 거친다
    assert result["사고_월"]["value"] == "11"
    # 답에 없는 칸은 빈칸
    assert result["이메일"] == {"value": "", "raw": "", "score": CERTAIN_SCORE}


def test_parse_response_without_json_raises():
    with pytest.raises(ValueError):
        parse_response("죄송합니다. 이미지를 읽을 수 없습니다.", "16")


def test_extract_fields_cli_uses_runner_with_image_path():
    seen = {}

    def fake_runner(prompt):
        seen["prompt"] = prompt
        return '{"values": {"진단명": "근염"}, "uncertain": []}'

    image = Image.new("RGB", (2480, 3508), "white")
    result = extract_fields_cli(image, "16", runner=fake_runner)
    assert result["진단명"]["value"] == "근염"
    assert ".png" in seen["prompt"]


def test_prompt_names_the_right_form():
    assert "위임장" in build_prompt("12", "a.png")
    assert "보험금 청구서" in build_prompt("16", "a.png")
