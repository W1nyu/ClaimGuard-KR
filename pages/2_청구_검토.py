"""화면 2: 청구 검토 — 담당자가 원본을 보며 값을 고치거나 확인하고, 불일치·위임 여부를 판단한 뒤 건을 확정한다.

재판단은 OCR을 다시 돌리지 않고 저장된 값으로만 계산한다.
"""
import streamlit as st

from src.audit import get_claim, list_claims
from src.bundle import finalize_claim, review_claim
from src.ui_common import (STATUS_LABELS, decision_badge, draw_fields, field_status, get_conn, load_entry_image,
                           review_order)

st.set_page_config(page_title="청구 검토", layout="wide")
st.title("청구 검토")

conn = get_conn()
waiting = list_claims(conn, status="검토대기")
st.write(f"검토 대기 {len(waiting)}건")
if not waiting:
    st.info("검토할 청구 건이 없습니다. '청구 접수' 화면에서 청구를 접수해 보세요.")
    st.stop()

labels = {f"{c['case_id']} · {c['claim']['type']} · {c.get('created_at', '')}": c["case_id"] for c in waiting}
case_id = labels[st.selectbox("청구 건", list(labels))]
bundle = get_claim(conn, case_id)
editor = st.text_input("담당자 이름", value="담당자", key="editor")

st.subheader(f"현재 결정: {decision_badge(bundle['decision'])}")
with st.expander(f"판단 사유 ({len(bundle['reasons'])}건)", expanded=True):
    for reason in bundle["reasons"]:
        st.write("- " + reason)

# ── 1. 담당자가 판단해야 할 것 ─────────────────────────────
st.markdown("### 1. 판단이 필요한 항목")
checks = {c["rule"]: c for c in bundle["checks"]}
delegation_choice = None
if "B01" in checks or bundle["review"].get("delegation") is not None:
    st.markdown("**위임 여부** — 청구서의 예금주와 피보험자 이름을 원본에서 확인하세요.")
    current = bundle["review"].get("delegation")
    options = ["자동 판단", "위임 필요", "위임 불필요"]
    index = 0 if current is None else (1 if current else 2)
    picked = st.radio("위임 여부", options, index=index, horizontal=True, key=f"delegation_{case_id}",
                      label_visibility="collapsed")
    delegation_choice = {"위임 필요": True, "위임 불필요": False}.get(picked)

mismatches = [c for c in bundle["checks"] if c["rule"] in ("B02", "B03", "B04", "B05") and c["status"] == "fail"]
confirmed = []
if mismatches:
    st.markdown("**청구서·위임장 불일치** — 원본을 보고 OCR 오류면 아래 값 표에서 고치고, 실제로 다르면 체크하세요.")
    for check in mismatches:
        already = check["rule"] in bundle["review"].get("confirmed_mismatches", [])
        if st.checkbox(f"{check['rule']} 실제 불일치 (고객에게 보완요청) — {check['message']}", value=already,
                       key=f"mismatch_{case_id}_{check['rule']}"):
            confirmed.append(check["rule"])
if "B01" not in checks and not mismatches:
    st.caption("위임·불일치 판단이 필요한 항목은 없습니다. 아래에서 확신도 낮은 칸을 확인하세요.")

# ── 2. 서류별 값 확인 ────────────────────────────────────
st.markdown("### 2. 서류별 값 확인")
st.caption("읽지 못한 칸과 확신도 낮은 칸부터 보여줍니다. 값이 틀리면 고치고, 맞으면(원본도 빈칸이면) '확인'에 체크하세요.")
edits, confirmed_fields = {}, {}
for index, document in enumerate(bundle["documents"]):
    if not document["extracted"]:
        continue
    low = sum(1 for f in document["extracted"].values() if f["score"] < 0.85 or (f.get("unread") and not f["value"]))
    with st.expander(f"{document['classified_type']} — 읽지 못했거나 확신도 낮은 칸 {low}개", expanded=low > 0):
        left, right = st.columns([3, 2])
        with left:
            rows = [{"칸": name, "값": field["value"], "확신도": field["score"], "상태": field_status(field),
                     "확인": field["score"] >= 1.0}
                    for name, field in sorted(document["extracted"].items(), key=lambda item: review_order(item[1]))]
            edited = st.data_editor(rows, hide_index=True, width="stretch", disabled=["칸", "확신도", "상태"],
                                    key=f"fields_{case_id}_{index}")
            edits[index] = {r["칸"]: r["값"] or "" for r in edited
                            if (r["값"] or "") != document["values"].get(r["칸"], "")}
            confirmed_fields[index] = [r["칸"] for r in edited if r["확인"]]
        with right:
            image = load_entry_image(document)
            if image is not None:
                st.image(draw_fields(image, document["form_code"], document["extracted"]), width="stretch")

if st.button("반영하고 다시 판단", type="primary"):
    review_claim(conn, case_id, editor=editor, edits={k: v for k, v in edits.items() if v},
                 confirmed_fields=confirmed_fields, confirmed_mismatches=confirmed, delegation=delegation_choice)
    st.rerun()

# ── 3. 확정 ───────────────────────────────────────────────
st.markdown("### 3. 최종 처리")
st.dataframe([{"규칙": c["rule"], "결과": STATUS_LABELS[c["status"]], "처리": c["action"], "내용": c["message"]}
              for c in bundle["checks"]], hide_index=True, width="stretch")
if bundle["customer_message"]:
    st.markdown("**고객 보완 안내문 (현재 기준)**")
    st.code(bundle["customer_message"], language=None)
final = st.radio("최종 처리", ["접수", "보완요청"], horizontal=True,
                 index=1 if bundle["customer_message"] else 0, key=f"final_{case_id}")
if st.button("확정하고 닫기"):
    finalize_claim(conn, case_id, editor=editor, final_decision=final)
    st.success("확정했습니다. 감사 로그에 기록됐습니다.")
    st.rerun()
