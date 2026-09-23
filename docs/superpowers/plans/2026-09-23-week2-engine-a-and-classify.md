# 2주차: 엔진 A(PaddleOCR Zone OCR) 추출·평가 + 서류 분류 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 청구서 이미지에서 칸별 값과 확신도를 뽑는 엔진 A와 서류 8종 분류기를 만들고, 검증용 데이터로 정확도·속도를 측정한다.

**Architecture:** 양식 칸 위치가 고정이므로 칸 영역을 잘라 PaddleOCR 한국어 인식 모델에 바로 넣는다(Zone OCR). 숫자 칸은 자주 헷갈리는 글자를 바로잡는다. 서류 분류는 이미지를 작은 흑백 썸네일로 줄여 양식별 평균 이미지와의 거리로 판별한다. 평가 스크립트가 1주차 정답 파일과 비교해 결과를 `results/`에 저장한다.

**Tech Stack:** Python 3.10, paddlepaddle 3.2.2, paddleocr 3.7.0 (`korean_PP-OCRv5_mobile_rec`), numpy, pytest

## Global Constraints

- 실행은 `.venv/Scripts/python`, 프로젝트 최상위에서.
- 함수 위주, 클래스 없음, 한국어 주석.
- `data/`, `.env`는 git 제외. `results/`의 집계 파일은 git 포함.
- Claude API 호출 금지.
- paddlepaddle은 3.2.2로 고정 (3.3.1은 CPU 가속(oneDNN) 버그로 실행 실패, 가속을 끄면 1장에 10분 이상).

## 설계서와 달라진 점 (탐색 결과 반영)

| 설계서 | 변경 | 이유 |
|---|---|---|
| 4.4 엔진 A: 전체 페이지 OCR → 박스를 칸에 배정 | 칸 영역을 잘라 인식 모델만 실행 (Zone OCR) | 전체 페이지 방식은 11.7초/장이고 인쇄 글자와 손글씨가 한 박스로 합쳐짐("492S년[\|월[2일"). Zone OCR은 0.7초/장, 칸이 섞이지 않음 |
| 4.3 서류 분류: 상단 제목 OCR 키워드 | 썸네일 이미지와 양식별 평균 이미지 거리 비교 | 8종 모두 인쇄 레이아웃이 고정이라 OCR 없이 수 밀리초에 판별 가능. 거리가 기준보다 멀면 `미분류` |

## 파일 구조

| 파일 | 역할 |
|---|---|
| `requirements.txt` (수정) | paddle 패키지 추가 |
| `src/extract_paddle.py` | 엔진 A: 칸 잘라 인식, 숫자 칸 보정 |
| `src/metrics.py` | 공백 제거 비교, 완전 일치, 글자 오류율(CER) |
| `src/classify.py` | 썸네일 벡터, 양식별 평균, 분류 |
| `scripts/build_classifier.py` | 학습 데이터로 평균 이미지·기준 거리 저장 |
| `scripts/run_eval.py` | 엔진 A 칸 정확도 평가, 분류 정확도 평가 |
| `tests/test_extract_paddle.py`, `tests/test_metrics.py`, `tests/test_classify.py` | 테스트 |

---

### Task 1: 평가 지표 (`metrics.py`)

**Files:**
- Create: `src/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Produces: `normalize(text) -> str`, `is_exact(pred, truth) -> bool`, `edit_distance(a, b) -> int`, `cer(pred, truth) -> float`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_metrics.py`:
```python
from src.metrics import cer, edit_distance, is_exact, normalize


def test_normalize_removes_all_spaces():
    assert normalize(" 의료법인 발해 병원 ") == "의료법인발해병원"


def test_is_exact_ignores_spaces():
    assert is_exact("자 전거 사고", "자전거사고")
    assert not is_exact("마키터", "마케터")


def test_edit_distance():
    assert edit_distance("마키터", "마케터") == 1
    assert edit_distance("", "abc") == 3
    assert edit_distance("kitten", "sitting") == 3


def test_cer_is_distance_over_truth_length():
    assert cer("마키터", "마케터") == 1 / 3
    assert cer("", "") == 0.0
    assert cer("잡음", "") == 1.0
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_metrics.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.metrics'`)

- [ ] **Step 3: 구현**

`src/metrics.py`:
```python
"""추출 결과를 정답과 비교하는 지표."""


def normalize(text):
    """모든 공백을 없앤다. 손글씨 띄어쓰기 차이는 오류로 보지 않는다."""
    return "".join(str(text).split())


def is_exact(pred, truth):
    return normalize(pred) == normalize(truth)


def edit_distance(a, b):
    """a를 b로 바꾸는 데 필요한 최소 글자 수정 횟수 (추가·삭제·교체)."""
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,                       # 삭제
                current[j - 1] + 1,                    # 추가
                previous[j - 1] + (char_a != char_b),  # 교체
            ))
        previous = current
    return previous[-1]


def cer(pred, truth):
    """글자 오류율 = 수정 횟수 / 정답 글자 수. 정답이 빈칸이면 예측도 빈칸일 때만 0."""
    pred, truth = normalize(pred), normalize(truth)
    if not truth:
        return 0.0 if not pred else 1.0
    return edit_distance(pred, truth) / len(truth)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_metrics.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/metrics.py tests/test_metrics.py
git commit -m "feat: 추출 평가 지표(완전 일치, CER)"
```

---

### Task 2: 엔진 A (`extract_paddle.py`)

**Files:**
- Modify: `requirements.txt`
- Create: `src/extract_paddle.py`
- Test: `tests/test_extract_paddle.py`

**Interfaces:**
- Consumes: `load_form_fields(form_code)` (1주차)
- Produces:
  - `clean_value(field: str, text: str) -> str`
  - `load_recognizer()` → PaddleOCR `TextRecognition` 객체 (한 번만 만들고 재사용)
  - `extract_fields(image: PIL.Image, form_code: str, recognizer=None) -> dict[str, dict]` — `{칸: {"value": str, "raw": str, "score": float}}`

- [ ] **Step 1: requirements.txt에 추가**

```
pillow
numpy
scikit-learn
pytest
paddlepaddle==3.2.2
paddleocr==3.7.0
```

Run: `.venv/Scripts/python -m pip install -r requirements.txt`

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_extract_paddle.py`:
```python
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
```

- [ ] **Step 3: 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_extract_paddle.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.extract_paddle'`)

- [ ] **Step 4: 구현**

`src/extract_paddle.py`:
```python
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
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_extract_paddle.py -q`
Expected: 4 passed

- [ ] **Step 6: 실제 이미지 1장 확인**

Run:
```bash
.venv/Scripts/python -c "from src.load_data import list_documents, load_image; from src.extract_paddle import extract_fields; d=[x for x in list_documents('val',['2-5.청구서']) if x['doc_id']=='IMG_OCR_6_F_0000416'][0]; r=extract_fields(load_image(d),'16'); print(r['주민번호'], r['사고_월'])"
```
Expected: `주민번호` 값 `598096-2264335`, `사고_월`은 숫자만 남음.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/extract_paddle.py tests/test_extract_paddle.py
git commit -m "feat: 엔진 A - PaddleOCR Zone OCR 칸별 추출"
```

---

### Task 3: 서류 분류 (`classify.py`, `build_classifier.py`)

**Files:**
- Create: `src/classify.py`, `scripts/build_classifier.py`
- Test: `tests/test_classify.py`
- Output (git 제외): `data/processed/classifier.npz`

**Interfaces:**
- Consumes: `list_documents`, `load_image`, `FORM_NAMES`, `PROJECT_ROOT` (1주차)
- Produces:
  - `thumbnail_vector(image) -> np.ndarray` (길이 62×88)
  - `build_centroids(vectors_by_code: dict[str, list[np.ndarray]]) -> tuple[dict[str, np.ndarray], float]` (양식별 평균, 미분류 기준 거리)
  - `classify(image, centroids, max_distance) -> tuple[str, float]` (양식 코드 또는 `"미분류"`, 거리)
  - `save_classifier(centroids, max_distance, path)`, `load_classifier(path=CLASSIFIER_PATH) -> tuple[dict, float]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_classify.py`:
```python
import numpy as np
from PIL import Image, ImageDraw

from src.classify import build_centroids, classify, load_classifier, save_classifier, thumbnail_vector


def form_image(bar_top):
    """흰 바탕에 검은 띠가 있는 가짜 양식. 띠 위치로 양식을 구분한다."""
    image = Image.new("RGB", (2480, 3508), "white")
    ImageDraw.Draw(image).rectangle([0, bar_top, 2480, bar_top + 400], fill="black")
    return image


def make_centroids():
    vectors = {
        "15": [thumbnail_vector(form_image(200)), thumbnail_vector(form_image(220))],
        "16": [thumbnail_vector(form_image(2800)), thumbnail_vector(form_image(2820))],
    }
    return build_centroids(vectors)


def test_thumbnail_vector_shape_and_range():
    vector = thumbnail_vector(form_image(200))
    assert vector.shape == (62 * 88,)
    assert 0.0 <= vector.min() and vector.max() <= 1.0


def test_classify_picks_nearest_form():
    centroids, max_distance = make_centroids()
    assert classify(form_image(210), centroids, max_distance)[0] == "15"
    assert classify(form_image(2810), centroids, max_distance)[0] == "16"


def test_far_image_is_unclassified():
    centroids, max_distance = make_centroids()
    black = Image.new("RGB", (2480, 3508), "black")
    assert classify(black, centroids, max_distance)[0] == "미분류"


def test_save_and_load(tmp_path):
    centroids, max_distance = make_centroids()
    path = tmp_path / "classifier.npz"
    save_classifier(centroids, max_distance, path)
    loaded, loaded_distance = load_classifier(path)
    assert set(loaded) == {"15", "16"}
    assert np.allclose(loaded["15"], centroids["15"])
    assert loaded_distance == max_distance
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_classify.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.classify'`)

- [ ] **Step 3: 구현**

`src/classify.py`:
```python
"""서류 8종 분류.

8종 모두 인쇄 양식이 고정돼 있어서, 이미지를 아주 작은 흑백 사진(62×88)으로 줄이면
손글씨는 거의 사라지고 양식 모양만 남는다. 양식별 평균 모양과 가장 가까운 것을 고른다.
"""
import numpy as np
from PIL import Image

from src.load_data import PROJECT_ROOT

THUMB_SIZE = (62, 88)  # 원본 2480×3508의 40분의 1
CLASSIFIER_PATH = PROJECT_ROOT / "data" / "processed" / "classifier.npz"
UNKNOWN = "미분류"
# 학습 서류 중 가장 먼 거리의 몇 배까지를 같은 양식으로 볼지
DISTANCE_MARGIN = 1.5


def thumbnail_vector(image):
    small = image.convert("L").resize(THUMB_SIZE, Image.Resampling.BILINEAR)
    return np.asarray(small, dtype=np.float32).flatten() / 255.0


def _distance(a, b):
    # 픽셀 수에 영향받지 않도록 평균 제곱 오차의 제곱근을 쓴다
    return float(np.sqrt(np.mean((a - b) ** 2)))


def build_centroids(vectors_by_code):
    centroids = {code: np.mean(vectors, axis=0) for code, vectors in vectors_by_code.items()}
    farthest = max(
        _distance(vector, centroids[code])
        for code, vectors in vectors_by_code.items()
        for vector in vectors
    )
    # 학습 이미지가 거의 같을 때 기준이 0이 되지 않도록 최소값을 둔다
    max_distance = max(farthest * DISTANCE_MARGIN, 0.05)
    return centroids, max_distance


def classify(image, centroids, max_distance):
    vector = thumbnail_vector(image)
    distances = {code: _distance(vector, centroid) for code, centroid in centroids.items()}
    best = min(distances, key=distances.get)
    if distances[best] > max_distance:
        return UNKNOWN, distances[best]
    return best, distances[best]


def save_classifier(centroids, max_distance, path=CLASSIFIER_PATH):
    np.savez(path, codes=np.array(list(centroids)), centroids=np.stack(list(centroids.values())), max_distance=max_distance)


def load_classifier(path=CLASSIFIER_PATH):
    data = np.load(path)
    centroids = {str(code): vector for code, vector in zip(data["codes"], data["centroids"])}
    return centroids, float(data["max_distance"])
```

`scripts/build_classifier.py`:
```python
"""학습 데이터에서 양식별로 30장씩 골라 평균 모양과 미분류 기준 거리를 저장한다.

실행: .venv/Scripts/python -m scripts.build_classifier
"""
from src.classify import CLASSIFIER_PATH, build_centroids, save_classifier, thumbnail_vector
from src.load_data import FORM_NAMES, list_documents, load_image

PER_FORM = 30


def main():
    vectors = {code: [] for code in FORM_NAMES}
    for doc in list_documents("train"):
        if len(vectors[doc["form_code"]]) < PER_FORM:
            vectors[doc["form_code"]].append(thumbnail_vector(load_image(doc)))
    centroids, max_distance = build_centroids(vectors)
    CLASSIFIER_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_classifier(centroids, max_distance)
    print(f"양식 {len(centroids)}종, 미분류 기준 거리 {max_distance:.4f} 저장: {CLASSIFIER_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인 + 분류기 만들기**

Run: `.venv/Scripts/python -m pytest tests/test_classify.py -q`
Expected: 4 passed

Run: `.venv/Scripts/python -m scripts.build_classifier`
Expected: `양식 8종, 미분류 기준 거리 0.0xxx 저장: ...`

- [ ] **Step 5: Commit**

```bash
git add src/classify.py scripts/build_classifier.py tests/test_classify.py
git commit -m "feat: 썸네일 거리 기반 서류 8종 분류"
```

---

### Task 4: 평가 스크립트 (`run_eval.py`)

**Files:**
- Create: `scripts/run_eval.py`
- Output: `data/processed/predictions/paddle_val_{15,16}.jsonl` (git 제외), `results/eval_engine_a_fields.csv`, `results/eval_summary.csv`, `results/eval_classify.csv` (git 포함)

**Interfaces:**
- Consumes: `extract_fields`, `load_recognizer` (Task 2), `is_exact`, `cer` (Task 1), `classify`, `load_classifier` (Task 3), 정답 JSONL (1주차)
- Produces: 예측 JSONL 한 줄 = `{"doc_id", "form_code", "engine": "paddle", "seconds": float, "fields": {칸: {"value","raw","score"}}}`. 3주차 결정 일치율 평가와 4주차 성능 화면이 읽는다. `eval_summary.csv` 열: `engine, form_code, documents, field_exact_rate, mean_cer, sec_per_doc, high_conf_share, high_conf_exact_rate`

- [ ] **Step 1: 스크립트 작성**

`scripts/run_eval.py`:
```python
"""엔진 A 추출 정확도와 서류 분류 정확도를 평가한다.

실행:
  .venv/Scripts/python -m scripts.run_eval extract   # 청구서 400장 (약 5분)
  .venv/Scripts/python -m scripts.run_eval classify  # 검증 서류 1,598장
"""
import csv
import json
import sys
import time
from collections import Counter

from src.classify import classify, load_classifier
from src.extract_paddle import extract_fields, load_recognizer
from src.load_data import PROJECT_ROOT, list_documents, load_image
from src.metrics import cer, is_exact

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
PRED_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
RESULTS = PROJECT_ROOT / "results"
# 이 확신도 이상인 칸만 자동 처리 후보로 본다 (설계서 4.8 기본값)
HIGH_CONFIDENCE = 0.85


def load_ground_truth(split, form_code):
    rows = {}
    with open(GT_DIR / f"{split}_{form_code}.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            rows[row["doc_id"]] = row["fields"]
    return rows


def run_extract():
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    recognizer = load_recognizer()
    field_rows = []
    summary_rows = []
    for form_code in ["15", "16"]:
        truth_by_doc = load_ground_truth("val", form_code)
        docs = [d for d in list_documents("val", ["2-5.청구서"]) if d["form_code"] == form_code]
        per_field = {}
        total_seconds = 0.0
        with open(PRED_DIR / f"paddle_val_{form_code}.jsonl", "w", encoding="utf-8") as out:
            for doc in docs:
                image = load_image(doc)
                start = time.perf_counter()
                extracted = extract_fields(image, form_code, recognizer)
                seconds = time.perf_counter() - start
                total_seconds += seconds
                out.write(json.dumps({"doc_id": doc["doc_id"], "form_code": form_code, "engine": "paddle",
                                      "seconds": round(seconds, 3), "fields": extracted}, ensure_ascii=False) + "\n")
                truth = truth_by_doc[doc["doc_id"]]
                for name, result in extracted.items():
                    expected = truth.get(name, "")
                    per_field.setdefault(name, []).append(
                        (is_exact(result["value"], expected), cer(result["value"], expected), result["score"]))

        all_results = [r for results in per_field.values() for r in results]
        high = [r for r in all_results if r[2] >= HIGH_CONFIDENCE]
        for name, results in per_field.items():
            field_rows.append({
                "form_code": form_code,
                "field": name,
                "documents": len(results),
                "exact_rate": round(sum(r[0] for r in results) / len(results), 3),
                "mean_cer": round(sum(r[1] for r in results) / len(results), 3),
            })
        summary_rows.append({
            "engine": "paddle",
            "form_code": form_code,
            "documents": len(docs),
            "field_exact_rate": round(sum(r[0] for r in all_results) / len(all_results), 3),
            "mean_cer": round(sum(r[1] for r in all_results) / len(all_results), 3),
            "sec_per_doc": round(total_seconds / len(docs), 2),
            "high_conf_share": round(len(high) / len(all_results), 3),
            "high_conf_exact_rate": round(sum(r[0] for r in high) / len(high), 3) if high else 0.0,
        })
        print(summary_rows[-1])

    _write_csv(RESULTS / "eval_engine_a_fields.csv", field_rows)
    _write_csv(RESULTS / "eval_summary.csv", summary_rows)


def run_classify():
    centroids, max_distance = load_classifier()
    confusion = Counter()
    docs = list_documents("val")
    for doc in docs:
        predicted, _ = classify(load_image(doc), centroids, max_distance)
        confusion[(doc["form_code"], predicted)] += 1
    correct = sum(count for (truth, pred), count in confusion.items() if truth == pred)
    rows = [{"truth": t, "predicted": p, "count": c} for (t, p), c in sorted(confusion.items())]
    _write_csv(RESULTS / "eval_classify.csv", rows)
    print(f"분류 정확도 {correct}/{len(docs)} = {correct / len(docs):.4f}")
    for row in rows:
        if row["truth"] != row["predicted"]:
            print("오분류:", row)


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    {"extract": run_extract, "classify": run_classify}[sys.argv[1]]()
```

- [ ] **Step 2: 분류 평가 실행**

Run: `.venv/Scripts/python -m scripts.run_eval classify`
Expected: 분류 정확도 0.99 이상. 오분류가 있으면 해당 서류 이미지를 확인하고 원인(구·신 청구서 혼동 등)을 결과 정리에 적는다.

- [ ] **Step 3: 추출 평가 실행**

Run: `.venv/Scripts/python -m scripts.run_eval extract`
Expected: 양식별 요약 2줄. `sec_per_doc` 약 1초 이하. `high_conf_exact_rate`가 `field_exact_rate`보다 높아야 확신도가 쓸모 있다는 뜻이다.

- [ ] **Step 4: 전체 테스트 + Commit**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 모든 테스트 통과

```bash
git add scripts/run_eval.py results/eval_engine_a_fields.csv results/eval_summary.csv results/eval_classify.csv
git commit -m "feat: 엔진 A·서류 분류 평가 스크립트와 결과"
```
