from PIL import Image, ImageDraw

from src.form_templates import load_form_fields
from src.ink import INK_THRESHOLD, apply_ink, field_ink, ink_ratio, unread_fields
from src.pipeline import with_ink_check


def form_image(written):
    """칸 배경을 옅은 노랑으로 칠하고, written 칸에만 검은 획을 그린 청구서(신) 이미지."""
    image = Image.new("RGB", (2480, 3508), "white")
    draw = ImageDraw.Draw(image)
    for name, (x0, y0, x1, y1) in load_form_fields("16").items():
        draw.rectangle((x0, y0, x1, y1), fill=(255, 250, 220))
        if name in written:
            # 손글씨 '1' 한 획 정도 (가장 적은 잉크)
            draw.line((x0 + 30, y0 + 20, x0 + 30, y1 - 20), fill="black", width=5)
    return image


def test_ink_ratio_ignores_background_color():
    assert ink_ratio([[200] * 10] * 10) == 0.0
    assert ink_ratio([[255] * 9 + [0]] * 10) == 0.1


def test_field_ink_finds_single_stroke_and_blank():
    ink = field_ink(form_image({"사고_월"}), "16")
    assert ink["사고_월"] >= INK_THRESHOLD
    assert ink["사고_일"] == 0.0


def test_apply_ink_marks_unread_and_clears_noise():
    extracted = {
        "사고_월": {"value": "", "raw": "'", "score": 0.1},      # 글씨가 있는데 못 읽음
        "사고_일": {"value": "1", "raw": "1", "score": 0.4},     # 글씨가 없는데 얼룩을 읽음
        "진단명": {"value": "멀미", "raw": "멀미", "score": 0.99},
    }
    result = apply_ink(extracted, {"사고_월": 0.01, "사고_일": 0.0, "진단명": 0.05})
    assert result["사고_월"]["unread"] is True
    assert result["사고_일"]["value"] == "" and result["사고_일"]["raw"] == "1" and result["사고_일"]["cleared"]
    assert result["진단명"]["value"] == "멀미" and "unread" not in result["진단명"]
    assert extracted["사고_일"]["value"] == "1"  # 원래 dict는 그대로
    assert unread_fields(result) == ["사고_월"]


def test_unread_clears_once_value_is_filled():
    assert unread_fields({"사고_월": {"value": "8", "unread": True, "score": 1.0}}) == []


def test_with_ink_check_wraps_engine():
    def engine(image, form_code):
        return {"사고_월": {"value": "", "raw": "", "score": 0.0}, "사고_일": {"value": "7", "raw": "7", "score": 0.5}}
    result = with_ink_check(engine)(form_image({"사고_월"}), "16")
    assert result["사고_월"]["unread"] is True
    assert result["사고_일"]["value"] == ""
