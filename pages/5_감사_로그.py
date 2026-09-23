"""화면 5: 감사 로그 — AI와 담당자의 결정, 값 수정 이력."""
import streamlit as st

from src.audit import list_decisions, list_edits
from src.ui_common import get_conn

st.set_page_config(page_title="감사 로그", layout="wide")
st.title("감사 로그")

conn = get_conn()
case_filter = st.text_input("서류 건 ID로 거르기 (비우면 전체)").strip() or None

decisions = list_decisions(conn, case_filter)
st.subheader(f"결정 이력 {len(decisions)}건")
st.dataframe(
    [{"시각": d["at"], "서류 건": d["case_id"], "주체": d["actor"], "엔진": d["engine"], "결정": d["decision"],
      "사유": " / ".join(d["reasons"])} for d in decisions],
    hide_index=True, width="stretch",
)

edits = list_edits(conn, case_filter)
st.subheader(f"수정 이력 {len(edits)}건")
st.dataframe(
    [{"시각": e["at"], "서류 건": e["case_id"], "칸": e["field"], "이전 값": e["old"], "새 값": e["new"],
      "수정자": e["editor"]} for e in edits],
    hide_index=True, width="stretch",
)
