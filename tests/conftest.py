"""테스트용 가짜 데이터 폴더를 만든다 (실제 데이터와 같은 구조, 아주 작게)."""
import io
import json
import zipfile

import pytest
from PIL import Image


def _png_bytes(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def fake_root(tmp_path):
    label = {
        "Images": {"form_type": "청구서", "width": 100, "height": 50},
        "bbox": [
            {"data": "홍길동", "id": 1, "x": [10, 10, 40, 40], "y": [5, 15, 5, 15]},
            {"data": "2024", "id": 2, "x": [50, 50, 80, 80], "y": [20, 30, 20, 30]},
        ],
    }
    for folder, img_prefix, lbl_prefix in [("Training", "TS", "TL"), ("Validation", "VS", "VL")]:
        img_dir = tmp_path / folder / "01.원천데이터"
        lbl_dir = tmp_path / folder / "02.라벨링데이터"
        img_dir.mkdir(parents=True)
        lbl_dir.mkdir(parents=True)
        with zipfile.ZipFile(img_dir / f"{img_prefix}_금융_2.보험_2-5.청구서.zip", "w") as z:
            z.writestr("/IMG_OCR_6_F_0000115.png", _png_bytes(100, 50))
            z.writestr("/IMG_OCR_6_F_0000216.png", _png_bytes(100, 50))
        with zipfile.ZipFile(lbl_dir / f"{lbl_prefix}_금융_2.보험_2-5.청구서.zip", "w") as z:
            z.writestr("/IMG_OCR_6_F_0000115.json", json.dumps(label, ensure_ascii=False))
            z.writestr("/IMG_OCR_6_F_0000216.json", json.dumps(label, ensure_ascii=False))
    return tmp_path
