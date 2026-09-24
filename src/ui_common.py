"""여러 화면이 같이 쓰는 도우미."""
import os
from pathlib import Path

import streamlit as st
from PIL import ImageDraw

from src.audit import AUDIT_DB, connect
from src.form_templates import load_form_fields
from src.load_data import PROJECT_ROOT

CASE_IMAGE_DIR = PROJECT_ROOT / "data" / "processed" / "case_images"
RESULTS_DIR = PROJECT_ROOT / "results"
DECISION_COLORS = {"자동접수": "green", "보완요청": "orange", "담당자검토": "red"}
STATUS_LABELS = {"pass": "통과", "fail": "위반", "unknown": "확인불가"}


@st.cache_resource
def _cached_connection(path):
    return connect(Path(path))


def get_conn():
    # 테스트에서는 환경변수로 임시 DB를 쓴다. DB 경로마다 연결을 따로 기억한다.
    return _cached_connection(os.environ.get("CLAIM_AUDIT_DB", str(AUDIT_DB)))


def decision_badge(decision):
    return f":{DECISION_COLORS.get(decision, 'gray')}[**{decision}**]"


def draw_fields(image, form_code, extracted, threshold=0.85):
    """칸 위치에 사각형을 그린다. 확신도가 기준 이상이면 초록, 미만이면 빨강."""
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    for name, rect in load_form_fields(form_code).items():
        field = extracted.get(name)
        if not field:
            continue
        color = "green" if field["score"] >= threshold else "red"
        draw.rectangle(rect, outline=color, width=6)
    canvas.thumbnail((1000, 1400))
    return canvas


def save_case_image(case_id, image):
    CASE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image.save(CASE_IMAGE_DIR / f"{case_id}.png")


def save_entry_images(entries, images):
    """청구 건 서류(entries)와 같은 순서의 원본 이미지를 각 서류의 image_id로 저장한다."""
    CASE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for entry, image in zip(entries, images):
        if image is not None and entry.get("image_id"):
            image.save(CASE_IMAGE_DIR / f"{entry['image_id']}.png")


def load_entry_image(entry):
    from PIL import Image
    path = CASE_IMAGE_DIR / f"{entry.get('image_id')}.png"
    return Image.open(path).convert("RGB") if entry.get("image_id") and path.exists() else None


def load_case_image(case_id):
    from PIL import Image
    path = CASE_IMAGE_DIR / f"{case_id}.png"
    return Image.open(path).convert("RGB") if path.exists() else None


def rules_table(rules):
    return [{
        "규칙": r["rule"], "결과": STATUS_LABELS[r["status"]], "처리": r["action"] if r["status"] != "pass" else "",
        "사유": r["message"], "칸": ", ".join(r["fields"]),
    } for r in rules]


def field_status(field):
    """잉크 판단 결과를 담당자에게 보여줄 말."""
    if field.get("unread") and not field.get("value"):
        return "읽지 못함 — 원본 확인"
    if field.get("cleared"):
        return "글씨 없음 — 인식 글자 비움"
    return ""


def review_order(field):
    """담당자 확인 순서: 읽지 못한 칸 먼저, 다음은 확신도 낮은 순."""
    return (not field.get("unread") or bool(field.get("value")), field["score"])


def fields_table(extracted):
    return [{"칸": name, "값": field["value"], "확신도": field["score"], "상태": field_status(field)}
            for name, field in extracted.items()]
