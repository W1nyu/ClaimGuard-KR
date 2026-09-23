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
