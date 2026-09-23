"""엔진 A: PaddleOCR(무료, 로컬)로 칸별 글자 읽기.

양식의 칸 위치가 고정돼 있으므로 칸 영역을 잘라 글자 인식 모델에 바로 넣는다(Zone OCR).
전체 페이지에서 글자 위치부터 찾는 방식보다 약 16배 빠르고(0.7초/장),
인쇄 글자와 손글씨가 한 덩어리로 묶이는 문제가 없다.
"""
import os

import numpy as np

from src.form_templates import load_form_fields

# 모델 서버 연결 확인을 건너뛴다 (이미 받은 모델을 그대로 사용)
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

MODEL_NAME = "korean_PP-OCRv5_mobile_rec"

# 숫자 칸: 칸 이름 → 숫자 외에 허용하는 기호
NUMERIC_FIELDS = {
    # 청구서(신) 16
    "사고_년": "", "사고_월": "", "사고_일": "", "사고_시": "", "사고_분": "",
    "작성_년": "", "작성_월": "", "작성_일": "", "주소_번지": "",
    "주민번호": "-", "연락처": "-", "계좌번호": "-",
    # 청구서(구) 15
    "청구_년": "", "청구_월": "", "청구_일": "", "증권번호": "",
    "사고일자": ".", "사고시각": ":",
}

# 손글씨 숫자를 인식할 때 자주 헷갈리는 글자 → 숫자
DIGIT_FIXES = str.maketrans({
    "|": "1", "l": "1", "I": "1", "(": "1", ")": "1", "[": "1", "]": "1",
    "O": "0", "o": "0", "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2",
})

_recognizer = None


def load_recognizer():
    """인식 모델은 불러오는 데 시간이 걸리므로 한 번만 만든다."""
    global _recognizer
    if _recognizer is None:
        from paddleocr import TextRecognition
        _recognizer = TextRecognition(model_name=MODEL_NAME)
    return _recognizer


def clean_value(field, text):
    text = text.strip()
    if field in NUMERIC_FIELDS:
        allowed = NUMERIC_FIELDS[field]
        text = text.translate(DIGIT_FIXES)
        text = "".join(ch for ch in text if ch.isdigit() or ch in allowed)
    return text


def extract_fields(image, form_code, recognizer=None):
    """칸마다 {값, 원본 인식 글자, 확신도}를 돌려준다."""
    recognizer = recognizer or load_recognizer()
    fields = load_form_fields(form_code)
    # PaddleOCR은 BGR 순서 배열을 받으므로 RGB를 뒤집는다
    crops = [np.array(image.crop(tuple(rect)))[:, :, ::-1] for rect in fields.values()]
    results = recognizer.predict(crops, batch_size=8)
    extracted = {}
    for name, result in zip(fields, results):
        raw = result["rec_text"]
        extracted[name] = {
            "value": clean_value(name, raw),
            "raw": raw,
            "score": round(float(result["rec_score"]), 4),
        }
    return extracted
