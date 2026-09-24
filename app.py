"""ClaimGuard-KR 시작 화면.

실행: .venv/Scripts/streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="ClaimGuard-KR", layout="wide")

st.title("ClaimGuard-KR")
st.subheader("사람 검토와 AI 위험평가를 갖춘 보험금 청구서류 접수 자동화")
st.markdown(
    """
DB손해보험 양식 서류(AI Hub 공개 데이터, 값은 가상)를 대상으로 한 **접수 단계 자동화 + AI 통제** 데모입니다.

| 단계 | 내용 |
|---|---|
| 서류 분류 | 8종 양식을 모양으로 판별 (검증 1,598장 100%) |
| 항목 추출 | 엔진 A: PaddleOCR(로컬) / 엔진 B: Claude(구독 CLI, 외부 모델) |
| 접수 검증 | 규칙 R01~R12 — 필수 칸(글씨는 있는데 못 읽은 칸은 담당자 확인), 날짜, 소멸시효, 주민번호, 연락처, 도로명주소, KCD-9 질병코드, KSCO 직업코드, 은행, 예금주 |
| 처리 결정 | 자동접수 / 보완요청(고객 안내문 자동 작성) / 담당자검토 |
| 통제 | 저확신 칸은 사람 검토, 모든 결정·수정은 감사 로그에 기록 |

왼쪽 메뉴에서 화면을 고르세요.
"""
)
st.info("데이터의 이름·주민번호·주소·계좌는 모두 가상 값입니다. 실제 고객 정보는 사용하지 않습니다.")
