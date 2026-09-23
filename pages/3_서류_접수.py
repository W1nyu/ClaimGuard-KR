"""화면 3: 서류 접수 (단건) — 서류를 고르거나 올리면 분류·추출·검증·결정 결과를 보여준다."""
from PIL import Image
import streamlit as st

from src.load_data import FORM_NAMES, list_documents, load_image
from src.pipeline import ENGINE_NAMES, process_document
from src.ui_common import decision_badge, draw_fields, fields_table, get_conn, rules_table, save_case_image

st.set_page_config(page_title="서류 접수 (단건)", layout="wide")
st.title("서류 접수 (단건)")
st.caption("서류 한 장을 처리합니다. 실제 청구는 '청구 접수' 화면에서 서류 묶음으로 처리하세요.")


@st.cache_data
def document_options():
    return {f"{d['doc_id']} · {FORM_NAMES[d['form_code']]}": d for d in list_documents("val")}


source = st.radio("서류 가져오기", ["검증 데이터에서 선택", "파일 업로드"], horizontal=True)
image, case_id = None, None
if source == "검증 데이터에서 선택":
    options = document_options()
    label = st.selectbox("서류", list(options))
    if label:
        doc = options[label]
        image, case_id = load_image(doc), doc["doc_id"]
else:
    uploaded = st.file_uploader("서류 이미지 (PNG/JPG)", type=["png", "jpg", "jpeg"])
    if uploaded:
        image = Image.open(uploaded).convert("RGB")

engine = st.radio("추출 엔진", list(ENGINE_NAMES), format_func=ENGINE_NAMES.get, horizontal=True)
st.caption("엔진 B는 이미지를 외부 모델로 보냅니다. 실패하거나 CLI가 없으면 엔진 A로 대신 처리합니다.")

if image is not None and st.button("처리 시작", type="primary"):
    with st.spinner("처리 중..."):
        case = process_document(image, engine=engine, case_id=case_id, conn=get_conn())
        save_case_image(case["case_id"], image)
    st.session_state["last_case"] = case
    st.session_state["last_image"] = image

case = st.session_state.get("last_case")
if case:
    left, right = st.columns([3, 2])
    with left:
        st.subheader(f"결정: {decision_badge(case['decision'])}")
        st.write(f"서류: {FORM_NAMES.get(case['form_code'], case['form_code'])} · 사용 엔진: {ENGINE_NAMES[case['engine']]}")
        if case["engine_note"]:
            st.warning(case["engine_note"])
        if case["reasons"]:
            st.markdown("**사유**")
            for reason in case["reasons"]:
                st.write("- " + reason)
        if case["customer_message"]:
            st.markdown("**고객 보완 안내문 (자동 작성)**")
            st.code(case["customer_message"], language=None)
        if case["extracted"]:
            st.markdown("**추출 값**")
            st.dataframe(fields_table(case["extracted"]), hide_index=True, width="stretch")
            st.markdown("**검증 규칙**")
            st.dataframe(rules_table(case["rules"]), hide_index=True, width="stretch")
    with right:
        shown = st.session_state["last_image"]
        if case["extracted"]:
            shown = draw_fields(shown, case["form_code"], case["extracted"])
            st.caption("초록: 확신도 0.85 이상 / 빨강: 담당자 확인 필요")
        st.image(shown, width="stretch")
