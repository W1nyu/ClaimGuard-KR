"""화면 4: 서류 검토 (단건) — 담당자가 값을 확인·수정하고 최종 처리를 확정한다."""
import streamlit as st

from src.audit import get_case, list_cases
from src.load_data import FORM_NAMES
from src.pipeline import approve, apply_edits
from src.ui_common import (decision_badge, draw_fields, field_status, get_conn, load_case_image, review_order,
                           rules_table)

st.set_page_config(page_title="서류 검토 (단건)", layout="wide")
st.title("서류 검토 (단건)")

conn = get_conn()
waiting = list_cases(conn, status="검토대기")
st.write(f"검토 대기 {len(waiting)}건")
if not waiting:
    st.info("검토할 서류가 없습니다. '서류 접수' 화면에서 서류를 처리해 보세요.")
    st.stop()

labels = {f"{c['case_id']} · {FORM_NAMES.get(c['form_code'], c['form_code'])} · {c['created_at']}": c["case_id"]
          for c in waiting}
case_id = labels[st.selectbox("서류 건", list(labels))]
case = get_case(conn, case_id)
editor = st.text_input("담당자 이름", value="담당자")

left, right = st.columns([3, 2])
with left:
    st.subheader(f"현재 결정: {decision_badge(case['decision'])}")
    for reason in case["reasons"]:
        st.write("- " + reason)
    if case["extracted"]:
        st.markdown("**값 확인·수정** (읽지 못한 칸, 확신도 낮은 칸부터)")
        rows = [{"칸": name, "값": field["value"], "확신도": field["score"], "상태": field_status(field)}
                for name, field in sorted(case["extracted"].items(), key=lambda item: review_order(item[1]))]
        edited = st.data_editor(rows, hide_index=True, width="stretch",
                                disabled=["칸", "확신도", "상태"], key=f"editor_{case_id}")
        if st.button("수정 반영 후 재검증"):
            new_values = {row["칸"]: row["값"] or "" for row in edited}
            case = apply_edits(conn, case_id, new_values, editor=editor)
            st.success(f"재검증 결과: {case['decision']}")
            st.rerun()
        st.markdown("**검증 규칙**")
        st.dataframe(rules_table(case["rules"]), hide_index=True, width="stretch")
    if case["customer_message"]:
        st.code(case["customer_message"], language=None)
    final = st.radio("최종 처리", ["접수", "보완요청"], horizontal=True)
    if st.button("확정하고 닫기", type="primary"):
        approve(conn, case_id, editor=editor, final_decision=final)
        st.success("처리를 확정했습니다. 감사 로그에 기록됐습니다.")
        st.rerun()
with right:
    image = load_case_image(case_id)
    if image is not None:
        if case["extracted"]:
            image = draw_fields(image, case["form_code"], case["extracted"])
        st.image(image, width="stretch")
