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

from src.load_data import CATEGORY_BY_FORM, PROJECT_ROOT, label_boxes, list_documents, load_image, load_label

OUT_DIR = PROJECT_ROOT / "data" / "processed" / "templates"


def collect_boxes(form_code):
    docs = [d for d in list_documents("train", [CATEGORY_BY_FORM[form_code]]) if d["form_code"] == form_code]
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
