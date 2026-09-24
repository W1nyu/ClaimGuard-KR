"""칸 안에 글씨(잉크)가 있는지 판단한다. OCR과 따로 이미지 픽셀만 본다.

OCR이 빈 글자를 돌려줘도 칸에 글씨가 있으면 '누락'이 아니라 '읽지 못함'이다.
누락으로 보면 고객에게 잘못된 보완요청이 가므로, 읽지 못한 칸은 담당자가 원본을 본다.

잉크 비율 = 칸 배경(밝은 쪽 90% 지점)보다 80 이상 어두운 픽셀의 비율.
배경색·스캔 밝기가 서류마다 달라도 배경 대비로 재므로 같은 기준을 쓸 수 있다.
검증 청구서 400장에서 글씨가 있는 칸은 최소 0.0073(손글씨 '1' 한 획), 빈칸은 0.0이었다.
"""
import numpy as np

from src.form_templates import load_form_fields

# 칸 테두리 선이 잘려 들어오지 않도록 안쪽으로 줄이는 픽셀
INSET = 4
DARKER_THAN_BACKGROUND = 80
INK_THRESHOLD = 0.003


def ink_ratio(gray):
    """흑백 픽셀 배열(0~255)에서 배경보다 확실히 어두운 픽셀의 비율."""
    gray = np.asarray(gray, dtype=np.int16)
    if gray.size == 0:
        return 0.0
    background = np.percentile(gray, 90)
    return float((gray < background - DARKER_THAN_BACKGROUND).mean())


def field_ink(image, form_code):
    """{칸 이름: 잉크 비율}"""
    gray = np.asarray(image.convert("L"))
    return {name: round(ink_ratio(gray[y0 + INSET:y1 - INSET, x0 + INSET:x1 - INSET]), 4)
            for name, (x0, y0, x1, y1) in load_form_fields(form_code).items()}


def apply_ink(extracted, ink):
    """추출 결과에 잉크 판단을 더한다. 원래 dict는 바꾸지 않는다.

    - 글씨가 있는데 값이 비었으면 unread=True (읽지 못함 → 담당자 확인)
    - 글씨가 없는데 값이 있으면 배경 얼룩을 읽은 것으로 보고 값을 비운다 (원래 인식 글자는 raw에 남음)
    """
    result = {}
    for name, field in extracted.items():
        field = dict(field)
        if name in ink:
            has_ink = ink[name] >= INK_THRESHOLD
            field["ink"] = ink[name]
            if has_ink and not field["value"]:
                field["unread"] = True
            elif not has_ink and field["value"]:
                field["value"] = ""
                field["cleared"] = True
        result[name] = field
    return result


def unread_fields(extracted):
    """글씨는 있지만 읽지 못한 칸. 담당자가 값을 넣거나 확인하면 빠진다."""
    return sorted(name for name, field in extracted.items() if field.get("unread") and not field.get("value"))
