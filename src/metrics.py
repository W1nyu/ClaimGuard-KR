"""추출 결과를 정답과 비교하는 지표."""

# 금액 칸은 숫자만 비교한다 (쓰는 사람마다 '원', 쉼표·마침표 표기가 달라 업무상 의미가 없다)
AMOUNT_FIELDS = {"가입금액", "타사가입금액"}
# 이메일 주소는 대소문자를 구분하지 않는다
CASE_INSENSITIVE_FIELDS = {"이메일"}


def normalize(text, field=None):
    """모든 공백을 없앤다. 손글씨 띄어쓰기 차이는 오류로 보지 않는다."""
    text = "".join(str(text).split())
    if field in AMOUNT_FIELDS:
        # '만원' 단위는 남겨 금액 크기가 달라지는 오류는 잡는다
        unit = "만" if "만" in text else ""
        text = "".join(ch for ch in text if ch.isdigit()) + unit
    elif field in CASE_INSENSITIVE_FIELDS:
        text = text.lower()
    return text


def is_exact(pred, truth, field=None):
    return normalize(pred, field) == normalize(truth, field)


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


def cer(pred, truth, field=None):
    """글자 오류율 = 수정 횟수 / 정답 글자 수. 정답이 빈칸이면 예측도 빈칸일 때만 0."""
    pred, truth = normalize(pred, field), normalize(truth, field)
    if not truth:
        return 0.0 if not pred else 1.0
    return edit_distance(pred, truth) / len(truth)
