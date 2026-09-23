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
