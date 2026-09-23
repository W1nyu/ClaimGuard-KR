"""양식별 칸 위치를 읽고, 글자 박스를 칸에 배정한다.

정답 만들기(라벨 박스)와 엔진 A(PaddleOCR 박스)가 같은 함수를 쓰므로 두 결과를 같은 기준으로 비교할 수 있다.
"""
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# 같은 줄로 볼 y 차이(픽셀). 손글씨 한 줄 높이(약 40~50px)보다 조금 작게 잡는다.
LINE_HEIGHT = 30


def load_form_fields(form_code):
    """config/form_fields_{양식코드}.json을 읽는다. {칸 이름: [x0, y0, x1, y1]}"""
    path = CONFIG_DIR / f"form_fields_{form_code}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _center(box):
    return (box["x0"] + box["x1"]) / 2, (box["y0"] + box["y1"]) / 2


def _find_field(box, fields):
    """박스 중심이 들어가는 칸을 찾는다. 여러 칸에 걸치면 가장 작은 칸을 고른다."""
    cx, cy = _center(box)
    matches = []
    for name, (x0, y0, x1, y1) in fields.items():
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            matches.append(((x1 - x0) * (y1 - y0), name))
    if not matches:
        return None
    return min(matches)[1]


def assign_boxes_to_fields(boxes, fields):
    """박스들을 칸에 나눠 담고, 칸마다 글자를 위→아래, 왼→오른 순으로 이어 붙인다."""
    grouped = {}
    unassigned = []
    for box in boxes:
        name = _find_field(box, fields)
        if name is None:
            unassigned.append(box)
        else:
            grouped.setdefault(name, []).append(box)

    values = {}
    for name, members in grouped.items():
        ordered = [b for line in _split_lines(members) for b in sorted(line, key=lambda b: b["x0"])]
        values[name] = " ".join(b["text"] for b in ordered)
    return values, unassigned


def _split_lines(boxes):
    """위에서부터 보며, 앞 박스와 y 차이가 LINE_HEIGHT 미만이면 같은 줄로 묶는다."""
    lines = []
    for box in sorted(boxes, key=lambda b: b["y0"]):
        if lines and box["y0"] - lines[-1][-1]["y0"] < LINE_HEIGHT:
            lines[-1].append(box)
        else:
            lines.append([box])
    return lines
