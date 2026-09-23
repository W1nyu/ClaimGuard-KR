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


def test_same_line_with_slightly_different_heights():
    # y0가 44와 46이면 같은 줄이다. 반올림 경계(45)를 사이에 두어도 왼→오른 순이어야 한다.
    boxes = [box("오른쪽", 200, 44, 280, 90), box("왼쪽", 10, 46, 100, 90)]
    values, _ = assign_boxes_to_fields(boxes, FIELDS)
    assert values["주소"] == "왼쪽 오른쪽"


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
