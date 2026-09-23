# 1주차: 데이터 읽기 + 항목별 정답 만들기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI Hub 보험 서류 zip을 그대로 읽고, 보험금 청구서 2종(양식 15·16)의 칸 위치를 정의해, 모든 청구서에 대해 "칸 이름 → 정답 값" 파일을 만든다.

**Architecture:** `src/load_data.py`가 zip 안의 이미지·라벨을 읽는다. `scripts/draft_templates.py`가 학습 라벨 박스 좌표를 군집화해 칸 위치 초안과 검수 이미지를 만든다. 사람이 검수해 `config/form_fields_{15,16}.json`에 칸 이름을 붙이면, `src/form_templates.py`가 박스를 칸에 배정하고 `scripts/build_ground_truth.py`가 정답 JSONL과 품질 보고서를 만든다.

**Tech Stack:** Python 3.10 (`.venv`), Pillow, numpy, scikit-learn(DBSCAN), pytest

## Global Constraints

- Python 3.10 가상환경 `.venv` 사용 (`py -3.10 -m venv .venv`). 실행은 `.venv/Scripts/python`.
- 코드는 파이썬 기초 수준 사용자가 읽을 수 있게: 함수 위주, 클래스 없음, 한국어 주석.
- `data/`와 `.env`는 git에 넣지 않는다. `config/`, `results/`(집계만)는 git에 넣는다.
- Claude API 호출 금지 (이번 주에는 해당 없음).
- 원본 zip은 풀지 않고 `zipfile`로 직접 읽는다.
- 모든 명령은 프로젝트 최상위 `C:\Users\Winyu\Documents\Project\insurance`에서 실행한다.

## 파일 구조

| 파일 | 역할 |
|---|---|
| `requirements.txt` | 패키지 목록 |
| `src/__init__.py`, `scripts/__init__.py` | 패키지 표시 (빈 파일) |
| `src/load_data.py` | 서류 목록, 이미지, 라벨, 라벨 박스 읽기 |
| `src/form_templates.py` | 칸 위치 설정 읽기, 박스 → 칸 배정 |
| `scripts/draft_templates.py` | 칸 위치 초안 + 검수 이미지 생성 |
| `config/form_fields_15.json`, `config/form_fields_16.json` | 확정된 칸 이름과 좌표 (검수 후 작성) |
| `scripts/build_ground_truth.py` | 정답 JSONL + 품질 보고서 |
| `tests/conftest.py`, `tests/test_load_data.py`, `tests/test_form_templates.py` | 테스트 |

---

### Task 1: 환경 설치 + 데이터 읽기 (`load_data.py`)

**Files:**
- Create: `requirements.txt`, `src/__init__.py`, `scripts/__init__.py`, `src/load_data.py`
- Test: `tests/conftest.py`, `tests/test_load_data.py`

**Interfaces:**
- Produces:
  - `DATA_ROOT: Path`
  - `FORM_NAMES: dict[str, str]` (양식 코드 → 이름)
  - `list_documents(split: str, categories: list[str] | None = None, root: Path = DATA_ROOT) -> list[dict]` — 각 dict 키: `doc_id, form_code, split, category, image_zip, image_name, label_zip, label_name`
  - `load_label(doc: dict) -> dict`
  - `load_image(doc: dict) -> PIL.Image.Image` (RGB)
  - `label_boxes(label: dict) -> list[dict]` — 각 dict 키: `text, x0, y0, x1, y1`

- [ ] **Step 1: 가상환경과 패키지 설치**

`requirements.txt`:
```
pillow
numpy
scikit-learn
pytest
```

Run:
```bash
py -3.10 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```
Expected: `Successfully installed ...`

`src/__init__.py`, `scripts/__init__.py`는 빈 파일로 만든다.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/conftest.py`:
```python
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
```

`tests/test_load_data.py`:
```python
from src.load_data import FORM_NAMES, label_boxes, list_documents, load_image, load_label


def test_list_documents_reads_label_zip(fake_root):
    docs = list_documents("val", ["2-5.청구서"], root=fake_root)
    assert [d["doc_id"] for d in docs] == ["IMG_OCR_6_F_0000115", "IMG_OCR_6_F_0000216"]
    assert [d["form_code"] for d in docs] == ["15", "16"]
    assert docs[0]["image_name"] == "/IMG_OCR_6_F_0000115.png"


def test_load_label_and_image(fake_root):
    doc = list_documents("train", ["2-5.청구서"], root=fake_root)[0]
    assert load_label(doc)["Images"]["form_type"] == "청구서"
    image = load_image(doc)
    assert image.size == (100, 50)
    assert image.mode == "RGB"


def test_label_boxes_uses_min_max():
    label = {"bbox": [{"data": "홍길동", "x": [40, 10, 10, 40], "y": [5, 15, 5, 15]}]}
    assert label_boxes(label) == [{"text": "홍길동", "x0": 10, "y0": 5, "x1": 40, "y1": 15}]


def test_form_names_has_eight_forms():
    assert len(FORM_NAMES) == 8
    assert FORM_NAMES["16"] == "보험금 청구서(신)"
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_load_data.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.load_data'`)

- [ ] **Step 4: 구현**

`src/load_data.py`:
```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_load_data.py -v`
Expected: 4 passed

- [ ] **Step 6: 실제 데이터로 확인**

Run:
```bash
.venv/Scripts/python -c "from src.load_data import *; d=list_documents('val',['2-5.청구서']); print(len(d)); print(len(label_boxes(load_label(d[0]))), load_image(d[0]).size)"
```
Expected: `400` 다음 줄에 박스 개수와 `(2480, 3508)`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src scripts tests
git commit -m "feat: AI Hub 보험 서류 zip 읽기 모듈"
```

---

### Task 2: 칸 위치 초안 만들기 (`draft_templates.py`)

**Files:**
- Create: `scripts/draft_templates.py`
- Output (git 제외): `data/processed/templates/draft_{code}.json`, `data/processed/templates/draft_{code}.png`

**Interfaces:**
- Consumes: `list_documents`, `load_label`, `label_boxes`, `load_image` (Task 1)
- Produces: `draft_{code}.json` — 목록, 각 항목 `{cluster, count, rect: [x0,y0,x1,y1], samples: [str, str, str]}`, y→x 순 정렬

이 스크립트는 탐색용이라 테스트 대신 결과 이미지로 검증한다.

- [ ] **Step 1: 스크립트 작성**

`scripts/draft_templates.py`:
```python
"""칸 위치 초안 만들기.

같은 양식의 학습 라벨 박스 중심점을 모두 모아 DBSCAN으로 묶으면, 한 칸에 쓴 글씨들이 한 덩어리가 된다.
덩어리마다 박스가 차지하는 범위를 칸 위치 초안으로 저장하고, 번호를 그린 검수 이미지를 만든다.

실행: .venv/Scripts/python -m scripts.draft_templates 16
"""
import json
import sys

import numpy as np
from PIL import ImageDraw
from sklearn.cluster import DBSCAN

from src.load_data import PROJECT_ROOT, label_boxes, list_documents, load_image, load_label

OUT_DIR = PROJECT_ROOT / "data" / "processed" / "templates"


def collect_boxes(form_code):
    docs = [d for d in list_documents("train", ["2-5.청구서"]) if d["form_code"] == form_code]
    boxes = []
    for doc in docs:
        boxes.extend(label_boxes(load_label(doc)))
    return docs, boxes


def cluster_boxes(boxes, doc_count, eps=40):
    centers = np.array([[(b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2] for b in boxes])
    # 전체 서류의 2% 이상에서 나타나는 위치만 칸으로 본다 (잡음 제거)
    min_samples = max(5, int(doc_count * 0.02))
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(centers)
    clusters = []
    for cluster_id in sorted(set(labels) - {-1}):
        members = [b for b, label in zip(boxes, labels) if label == cluster_id]
        x0 = int(np.percentile([b["x0"] for b in members], 1)) - 10
        y0 = int(np.percentile([b["y0"] for b in members], 1)) - 10
        x1 = int(np.percentile([b["x1"] for b in members], 99)) + 10
        y1 = int(np.percentile([b["y1"] for b in members], 99)) + 10
        clusters.append({
            "count": len(members),
            "rect": [x0, y0, x1, y1],
            "samples": [m["text"] for m in members[:3]],
        })
    clusters.sort(key=lambda c: (c["rect"][1] // 30, c["rect"][0]))
    for number, cluster in enumerate(clusters):
        cluster["cluster"] = number
    noise = int((labels == -1).sum())
    return clusters, noise


def draw_review_image(doc, clusters, path):
    image = load_image(doc)
    draw = ImageDraw.Draw(image)
    for c in clusters:
        draw.rectangle(c["rect"], outline="red", width=4)
        draw.text((c["rect"][0] + 4, c["rect"][1] - 30), str(c["cluster"]), fill="red", font_size=32)
    image.thumbnail((1400, 2000))
    image.save(path)


def main(form_code):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docs, boxes = collect_boxes(form_code)
    clusters, noise = cluster_boxes(boxes, len(docs))
    (OUT_DIR / f"draft_{form_code}.json").write_text(json.dumps(clusters, ensure_ascii=False, indent=1), encoding="utf-8")
    draw_review_image(docs[0], clusters, OUT_DIR / f"draft_{form_code}.png")
    print(f"양식 {form_code}: 서류 {len(docs)}장, 박스 {len(boxes)}개, 칸 후보 {len(clusters)}개, 잡음 박스 {noise}개")
    for c in clusters:
        print(c["cluster"], c["count"], c["rect"], c["samples"])


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 2: 두 양식에 대해 실행**

Run:
```bash
.venv/Scripts/python -m scripts.draft_templates 15
.venv/Scripts/python -m scripts.draft_templates 16
```
Expected: 양식별 요약 한 줄 + 칸 후보 목록. 잡음 박스가 전체의 1% 미만이어야 한다. 1%를 넘거나, 검수 이미지에서 두 칸이 한 덩어리로 합쳐졌으면 `eps`를 25~60 사이에서 조정해 다시 실행한다.

- [ ] **Step 3: 검수 이미지 확인**

`data/processed/templates/draft_15.png`, `draft_16.png`를 열어 각 빨간 사각형이 양식의 칸 하나에만 해당하는지 확인한다. 칸 후보 수가 설계서 4.2의 칸 목록과 비슷해야 한다(15: 약 23개, 16: 약 33개).

- [ ] **Step 4: Commit**

```bash
git add scripts/draft_templates.py
git commit -m "feat: 라벨 박스 군집화로 칸 위치 초안 생성"
```

---

### Task 3: 칸 이름 확정 + 박스→칸 배정 (`form_templates.py`)

**Files:**
- Create: `config/form_fields_15.json`, `config/form_fields_16.json`, `src/form_templates.py`
- Test: `tests/test_form_templates.py`

**Interfaces:**
- Consumes: `draft_{code}.json` (Task 2)
- Produces:
  - `load_form_fields(form_code: str) -> dict[str, list[int]]` (칸 이름 → `[x0, y0, x1, y1]`)
  - `assign_boxes_to_fields(boxes: list[dict], fields: dict[str, list[int]]) -> tuple[dict[str, str], list[dict]]` — (칸별 값, 어느 칸에도 안 들어간 박스). 박스의 다른 키(예: `score`)는 무시한다. 칸별 확신도는 2주차 엔진 A에서 추가한다.

- [ ] **Step 1: 설정 파일 작성**

`draft_{code}.json`의 각 `cluster` 번호를 검수 이미지와 대조해 설계서 4.2의 칸 이름을 붙인다. 형식:
```json
{
  "피보험자_성명": [600, 690, 1040, 770],
  "주민번호": [1230, 690, 1760, 770]
}
```
좌표는 draft의 `rect`를 그대로 쓴다. 한 칸이 두 덩어리로 나뉘었으면 두 rect를 감싸는 사각형으로 합친다. 칸 이름은 설계서 4.2 목록을 따른다.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_form_templates.py`:
```python
from src.form_templates import assign_boxes_to_fields, load_form_fields

FIELDS = {
    "성명": [0, 0, 100, 50],
    "주민번호": [100, 0, 300, 50],
    "주소": [0, 50, 300, 150],
}


def box(text, x0, y0, x1, y1):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1}


def test_box_goes_to_field_containing_its_center():
    values, unassigned = assign_boxes_to_fields([box("홍길동", 10, 10, 60, 40)], FIELDS)
    assert values == {"성명": "홍길동"}
    assert unassigned == []


def test_multiple_boxes_joined_left_to_right():
    boxes = [box("강남구", 120, 60, 200, 90), box("서울시", 10, 60, 100, 90)]
    values, _ = assign_boxes_to_fields(boxes, FIELDS)
    assert values["주소"] == "서울시 강남구"


def test_multiple_lines_joined_top_to_bottom():
    boxes = [box("둘째줄", 10, 110, 90, 140), box("첫째줄", 150, 60, 250, 90)]
    values, _ = assign_boxes_to_fields(boxes, FIELDS)
    assert values["주소"] == "첫째줄 둘째줄"


def test_box_outside_every_field_is_unassigned():
    outside = box("잡음", 400, 400, 450, 450)
    values, unassigned = assign_boxes_to_fields([outside], FIELDS)
    assert values == {}
    assert unassigned == [outside]


def test_overlapping_fields_pick_smallest():
    fields = {"큰칸": [0, 0, 300, 300], "작은칸": [0, 0, 100, 100]}
    values, _ = assign_boxes_to_fields([box("값", 10, 10, 50, 50)], fields)
    assert values == {"작은칸": "값"}


def test_real_config_files_exist():
    for code in ["15", "16"]:
        fields = load_form_fields(code)
        assert len(fields) >= 15
        for rect in fields.values():
            x0, y0, x1, y1 = rect
            assert 0 <= x0 < x1 <= 2480 and 0 <= y0 < y1 <= 3508
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_form_templates.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.form_templates'`)

- [ ] **Step 4: 구현**

`src/form_templates.py`:
```python
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
        members.sort(key=lambda b: (round(b["y0"] / LINE_HEIGHT), b["x0"]))
        values[name] = " ".join(b["text"] for b in members)
    return values, unassigned
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_form_templates.py -v`
Expected: 6 passed. `test_multiple_lines_joined_top_to_bottom`가 실패하면 `LINE_HEIGHT`와 테스트 좌표(y0 60 vs 110)를 확인한다.

- [ ] **Step 6: Commit**

```bash
git add config src/form_templates.py tests/test_form_templates.py
git commit -m "feat: 청구서 칸 위치 확정과 박스-칸 배정"
```

---

### Task 4: 정답 파일 + 품질 보고서 (`build_ground_truth.py`)

**Files:**
- Create: `scripts/build_ground_truth.py`
- Output: `data/processed/ground_truth/{split}_{code}.jsonl` (git 제외), `results/ground_truth_report.csv` (git 포함)

**Interfaces:**
- Consumes: `list_documents`, `load_label`, `label_boxes` (Task 1), `load_form_fields`, `assign_boxes_to_fields` (Task 3)
- Produces: JSONL 한 줄 = `{"doc_id": str, "form_code": str, "split": str, "fields": {칸: 값}}`. 2주차 평가 스크립트가 이 파일을 정답으로 읽는다.

- [ ] **Step 1: 스크립트 작성**

`scripts/build_ground_truth.py`:
```python
"""라벨 박스를 칸에 배정해 청구서 항목별 정답 파일을 만든다.

실행: .venv/Scripts/python -m scripts.build_ground_truth
"""
import csv
import json

from src.form_templates import assign_boxes_to_fields, load_form_fields
from src.load_data import PROJECT_ROOT, label_boxes, list_documents, load_label

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
REPORT_PATH = PROJECT_ROOT / "results" / "ground_truth_report.csv"


def build(split, form_code):
    fields = load_form_fields(form_code)
    docs = [d for d in list_documents(split, ["2-5.청구서"]) if d["form_code"] == form_code]
    total_boxes = 0
    unassigned_boxes = 0
    filled = {name: 0 for name in fields}
    out_path = GT_DIR / f"{split}_{form_code}.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for doc in docs:
            boxes = label_boxes(load_label(doc))
            values, unassigned = assign_boxes_to_fields(boxes, fields)
            total_boxes += len(boxes)
            unassigned_boxes += len(unassigned)
            for name in values:
                filled[name] += 1
            row = {"doc_id": doc["doc_id"], "form_code": form_code, "split": split, "fields": values}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "split": split,
        "form_code": form_code,
        "documents": len(docs),
        "boxes": total_boxes,
        "unassigned_boxes": unassigned_boxes,
        "unassigned_rate": round(unassigned_boxes / total_boxes, 4),
        "fill_rate": filled,
    }


def main():
    GT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for split in ["train", "val"]:
        for form_code in ["15", "16"]:
            summary = build(split, form_code)
            print(f"{split} {form_code}: 서류 {summary['documents']}장, 배정 실패 {summary['unassigned_rate']:.2%}")
            for name, count in summary["fill_rate"].items():
                rows.append({
                    "split": split,
                    "form_code": form_code,
                    "field": name,
                    "fill_rate": round(count / summary["documents"], 3),
                    "unassigned_rate": summary["unassigned_rate"],
                })
    with open(REPORT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "form_code", "field", "fill_rate", "unassigned_rate"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"보고서 저장: {REPORT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

Run: `.venv/Scripts/python -m scripts.build_ground_truth`
Expected: 4줄 (train/val × 15/16) 모두 `배정 실패` 1% 미만. 서류 수: train 15 = 1598, train 16 = 1603, val 15 = 209, val 16 = 191.

1% 이상이면 배정 실패 박스를 확인해 칸 좌표를 넓히거나 빠진 칸을 `config/form_fields_{code}.json`에 추가하고 다시 실행한다.

- [ ] **Step 3: 정답 샘플 눈으로 확인**

Run:
```bash
.venv/Scripts/python -c "import json; print(json.dumps(json.loads(open('data/processed/ground_truth/val_16.jsonl',encoding='utf-8').readline()), ensure_ascii=False, indent=1))"
```
Expected: 해당 이미지와 값이 맞는지 칸 5개 이상 대조.

- [ ] **Step 4: 전체 테스트 + Commit**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 10 passed

```bash
git add scripts/build_ground_truth.py results/ground_truth_report.csv
git commit -m "feat: 청구서 항목별 정답 생성과 품질 보고서"
```

---

## 다음 계획 (주차별로 따로 작성)

- 2주차: 엔진 A(PaddleOCR) 추출·평가, 서류 분류
- 3주차: reference(KCD-9·KSCO·은행·도로명주소), validate(R01~R11), route + 테스트
- 4주차: 엔진 B(세션 처리·CLI), audit, Streamlit 화면 1·2·3·5
- 5주차: risk_assessment(H)·화면 4, 결과 정리, README
