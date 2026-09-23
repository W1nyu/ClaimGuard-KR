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
