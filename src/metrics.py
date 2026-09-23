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
