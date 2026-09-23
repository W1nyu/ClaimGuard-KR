"""AI Hub 'OCR 데이터(금융 및 물류)'의 보험 서류를 zip에서 바로 읽는 함수 모음.

zip을 풀지 않아도 되도록, 필요한 파일만 그때그때 꺼내 읽는다.
"""
import io
import json
import zipfile
from functools import lru_cache
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "reference" / "025.OCR 데이터(금융 및 물류)" / "01-1.정식개방데이터"

# 파일명 끝 두 자리 = 양식 코드. 8종 모두 DB손해보험 양식이다.
FORM_NAMES = {
    "11": "자동이체신청서",
    "12": "위임장",
    "13": "보험계약대출 승계 동의서",
    "14": "간병인 지원 서비스 신청서",
    "15": "보험금 청구서(구)",
    "16": "보험금 청구서(신)",
    "17": "도난(파손)사실 확인서",
    "18": "합의서",
}

# zip 파일 이름에 들어가는 서류 분류
CATEGORIES = ["2-1.신청서", "2-2.확인서", "2-3.위임장", "2-4.동의서", "2-5.청구서", "2-6.합의서"]

# split 이름 → (폴더, 이미지 zip 접두어, 라벨 zip 접두어)
SPLITS = {"train": ("Training", "TS", "TL"), "val": ("Validation", "VS", "VL")}


def _zip_paths(split, category, root):
    folder, image_prefix, label_prefix = SPLITS[split]
    base = Path(root) / folder
    image_zip = base / "01.원천데이터" / f"{image_prefix}_금융_2.보험_{category}.zip"
    label_zip = base / "02.라벨링데이터" / f"{label_prefix}_금융_2.보험_{category}.zip"
    return image_zip, label_zip


@lru_cache(maxsize=32)
def _open_zip(path):
    # 같은 zip을 여러 번 열지 않도록 한 번 연 것을 기억해 둔다.
    return zipfile.ZipFile(path)


def list_documents(split, categories=None, root=DATA_ROOT):
    """서류 목록을 만든다. split은 'train' 또는 'val'."""
    documents = []
    for category in categories or CATEGORIES:
        image_zip, label_zip = _zip_paths(split, category, root)
        names = sorted(n for n in _open_zip(str(label_zip)).namelist() if n.endswith(".json"))
        for name in names:
            doc_id = name.strip("/").removesuffix(".json")
            documents.append({
                "doc_id": doc_id,
                "form_code": doc_id[-2:],
                "split": split,
                "category": category,
                "image_zip": str(image_zip),
                "image_name": name.removesuffix(".json") + ".png",
                "label_zip": str(label_zip),
                "label_name": name,
            })
    return documents


def load_label(doc):
    """라벨 JSON을 dict로 읽는다."""
    return json.loads(_open_zip(doc["label_zip"]).read(doc["label_name"]))


def load_image(doc):
    """서류 이미지를 RGB 이미지로 읽는다."""
    data = _open_zip(doc["image_zip"]).read(doc["image_name"])
    return Image.open(io.BytesIO(data)).convert("RGB")


def label_boxes(label):
    """라벨의 4점 좌표를 (왼쪽 위 x0,y0 / 오른쪽 아래 x1,y1) 사각형으로 바꾼다."""
    boxes = []
    for box in label["bbox"]:
        boxes.append({
            "text": box["data"],
            "x0": min(box["x"]),
            "y0": min(box["y"]),
            "x1": max(box["x"]),
            "y1": max(box["y"]),
        })
    return boxes
