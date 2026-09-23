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
