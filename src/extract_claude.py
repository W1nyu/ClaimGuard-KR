"""엔진 B: Claude(구독)로 칸별 글자 읽기.

Claude API는 쓰지 않는다. PC에 설치된 Claude Code CLI(`claude -p`)에 이미지 파일 경로를 주고
Read 도구로 이미지를 보게 한 뒤, 칸별 값을 JSON으로 답하게 한다.
외부 모델로 이미지를 보내는 방식이라 AI 위험평가(H)에서 별도 시나리오로 평가한다.
"""
import json
import re
import shutil
import subprocess
import uuid

from src.extract_paddle import clean_value
from src.form_templates import load_form_fields
from src.load_data import PROJECT_ROOT

TMP_DIR = PROJECT_ROOT / "data" / "processed" / "tmp"
LONG_SIDE = 1600
# 모델이 '불확실'하다고 한 칸과 아닌 칸의 확신도 (엔진 A 확신도와 같은 0~1 척도로 맞춤)
CERTAIN_SCORE = 0.95
UNCERTAIN_SCORE = 0.5

# 손글씨 칸이 있는 세로 범위만 잘라서 보낸다 (글씨가 더 크게 보이도록)
CROP_BOX = {"16": (0, 640, 2480, 3120), "15": (0, 450, 2480, 1800), "12": (0, 560, 2480, 2640)}

# 칸 이름 → 양식에서 그 칸을 찾는 설명
FIELD_GUIDE = {
    "12": {
        "위임사항_피보험자": "1번 위임사항의 '피보험자 ___ 의' 이름", "사고_년": "위임사항 사고의 '년' 앞 숫자",
        "사고_월": "위임사항 사고의 '월' 앞 숫자", "사고_일": "위임사항 사고의 '일' 앞 숫자",
        "보험상품명": "표의 '보험 상품명' 첫 줄", "증권번호": "표의 '증권번호' 첫 줄", "계약자명": "표의 '계약자명' 첫 줄",
        "피보험자명": "표의 '피보험자명' 첫 줄", "작성_년": "'작성일자'의 '년' 앞 숫자",
        "작성_월": "'작성일자'의 '월' 앞 숫자", "작성_일": "'작성일자'의 '일' 앞 숫자",
        "위임인_성명": "2번 위임하는 분의 첫 줄 '성명'", "위임인_주민번호": "2번 위임하는 분의 첫 줄 '주민등록번호'",
        "위임인_연락처": "2번 위임하는 분의 첫 줄 '연락처'", "수임인_성명": "3번 위임받는 분의 '성명'",
        "수임인_주민번호": "3번 위임받는 분의 '주민등록번호'", "수임인_연락처": "3번 위임받는 분의 '연락처'",
        "수임인_관계": "3번 위임받는 분의 '피보험자와 관계'", "수임인_은행명": "3번 '수령계좌'의 '은행명'",
        "수임인_계좌번호": "3번 '수령계좌'의 '계좌번호'",
    },
    "16": {
        "피보험자_성명": "1번 인적사항의 '성명'", "주민번호": "'주민번호'", "회사명": "'회사명'",
        "부서명": "'부서명'", "직업": "'하시는 일'",
        "주소_시도": "'주소' 칸의 첫 번째 부분(시·도)", "주소_시군구": "'주소' 칸의 두 번째 부분(시·군·구)",
        "주소_도로명": "'주소' 칸의 세 번째 부분(도로명·동·리)", "주소_번지": "'주소' 칸의 네 번째 부분(번지)",
        "보상안내_성명": "보상안내 받으실 분의 '기타 (성명: )'", "보상안내_관계": "'피보험자와의 관계'",
        "연락처": "'연락처'", "이메일": "'E-mail'", "타사보험1": "2번 다른 보험회사의 '1( )' 안",
        "사고_년": "사고발생일의 '년' 앞 숫자", "사고_월": "사고발생일의 '월' 앞 숫자",
        "사고_일": "사고발생일의 '일' 앞 숫자", "사고_시": "사고발생일의 '시' 앞 숫자",
        "사고_분": "사고발생일의 '분' 앞 숫자", "진단명": "'진단명(병명/증상)'", "사고장소": "'사고장소'",
        "치료병원": "'치료병원'", "사고경위": "'사고경위(상해)/아픈부위(질병)'", "계좌번호": "4번의 '계좌번호'",
        "은행명": "4번의 '은행명'", "예금주": "4번의 '예금주'", "작성_년": "'작성일'의 '년' 앞 숫자",
        "작성_월": "'작성일'의 '월' 앞 숫자", "작성_일": "'작성일'의 '일' 앞 숫자", "청구권자": "'청구권자' 서명란의 이름",
    },
    "15": {
        "보험종목": "1번의 '보험종목'", "증권번호": "1번의 '증권번호'", "계약자": "1번의 '보험계약자'",
        "가입금액": "1번의 '보험가입금액'", "타사보험회사": "2번의 '보험회사'", "타사가입금액": "2번의 '보험가입금액'",
        "사고일자": "3번 '사고일시'의 날짜 부분", "사고시각": "3번 '사고일시'의 시각 부분", "사고원인": "'사고원인'",
        "사고장소": "'사고장소'", "사고경위": "'사고경위'", "청구_년": "청구일 '20 __ 년'의 손글씨 두 자리",
        "청구_월": "청구일의 '월' 앞 숫자", "청구_일": "청구일의 '일' 앞 숫자", "청구인_성명": "'보험금 청구인 성명'",
        "이메일": "'e-mail'", "관계": "'피보험자와의 관계'", "주소_시도": "'주소'의 첫 번째 부분(시·도)",
        "주소_시군구": "'주소'의 두 번째 부분(시·군·구)", "주소_도로명": "'주소'의 세 번째 부분(도로명)",
        "주소_번지": "'주소'의 네 번째 부분(번지)", "연락처": "'연락처'",
    },
}


FORM_TITLES = {"12": "위임장", "15": "보험금 청구서", "16": "보험금 청구서"}


def build_prompt(form_code, image_path):
    fields = load_form_fields(form_code)
    guide = "\n".join(f"- {name}: {FIELD_GUIDE[form_code][name]}" for name in fields)
    return (
        f"이미지 파일 {image_path} 를 Read 도구로 열어 보세요. DB손해보험 {FORM_TITLES[form_code]}의 일부입니다.\n"
        "아래 각 칸에 손으로 쓴 값을 읽어 주세요.\n"
        "규칙:\n"
        "1. 쓰인 그대로 옮기세요. 날짜·주소·이름이 이상해 보여도 절대 고치지 마세요 (예: 4925년도 그대로).\n"
        "2. 비어 있는 칸은 빈 문자열 \"\"로 두세요.\n"
        "3. 인쇄된 글자(년, 월, 원 등)는 넣지 말고 손글씨만 넣으세요. 단, 손글씨에 포함된 기호(-, ., :, @, 만원)는 그대로 두세요.\n"
        "4. 글씨가 흐리거나 확신이 없는 칸은 uncertain 목록에 칸 이름을 넣으세요.\n"
        f"칸 목록:\n{guide}\n"
        '다른 설명 없이 JSON 하나만 답하세요: {"values": {"칸 이름": "값", ...}, "uncertain": ["칸 이름", ...]}'
    )


def prepare_image(image, form_code):
    cropped = image.crop(CROP_BOX[form_code])
    cropped.thumbnail((LONG_SIDE, LONG_SIDE))
    return cropped


def parse_response(text, form_code):
    """응답에서 JSON을 찾아 엔진 A와 같은 {칸: {value, raw, score}} 모양으로 바꾼다."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("응답에서 JSON을 찾지 못했습니다")
    data = json.loads(match.group(0))
    values = data.get("values", {})
    uncertain = set(data.get("uncertain", []))
    result = {}
    for name in load_form_fields(form_code):
        raw = str(values.get(name) or "")
        result[name] = {
            "value": clean_value(name, raw),
            "raw": raw,
            "score": UNCERTAIN_SCORE if name in uncertain else CERTAIN_SCORE,
        }
    return result


def _run_claude(prompt, timeout=60):
    executable = shutil.which("claude")
    if executable is None:
        raise FileNotFoundError("claude CLI를 찾을 수 없습니다")
    completed = subprocess.run(
        [executable, "-p", prompt, "--allowedTools", "Read", "--output-format", "text"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"claude CLI 실패: {completed.stderr.strip()[:200]}")
    return completed.stdout


def extract_fields_cli(image, form_code, runner=None, timeout=60):
    """이미지를 임시 파일로 저장하고 claude CLI에 읽게 한다. runner를 주면 그것을 대신 호출한다."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"claude_input_{uuid.uuid4().hex}.png"
    prepare_image(image, form_code).save(path)
    try:
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        prompt = build_prompt(form_code, relative)
        text = runner(prompt) if runner else _run_claude(prompt, timeout)
        return parse_response(text, form_code)
    finally:
        path.unlink(missing_ok=True)
