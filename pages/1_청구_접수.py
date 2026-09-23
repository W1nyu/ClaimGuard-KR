"""화면 1: 청구 접수 — 청구 정보와 서류 묶음을 받아 구비서류 완비와 서류 간 대조를 판단한다.

보완대기 건에는 '보완 서류 제출'로 빠진 서류를 추가로 낼 수 있다(같은 건에 붙여 다시 판단).
"""
from PIL import Image
import streamlit as st

from src.audit import get_claim, list_claims
from src.bundle import process_claim, resubmit_claim
from src.claim_docs import CLAIM_ITEMS, INJURY_CAUSES, check_completeness, document_catalog, required_documents
from src.load_data import list_documents, load_image
from src.pipeline import ENGINE_NAMES
from src.ui_common import STATUS_LABELS, decision_badge, draw_fields, get_conn, rules_table, save_entry_images

st.set_page_config(page_title="청구 접수", layout="wide")
st.title("청구 접수")
st.caption("장기보험(질병·상해) 청구 한 건을 서류 묶음으로 받습니다. 필요 서류 기준: DB손해보험 '보험금청구서류 안내'. "
           "의료기관·관공서 서류는 공개 데이터에 이미지가 없어 서류 종류만 받고 내용은 읽지 않습니다.")


@st.cache_data
def sample_documents():
    # 신양식(16)을 먼저 보여준다: 예금주 칸이 있어 위임 판단과 위임장 대조가 가능하다 (구양식 15는 불가)
    ordered = sorted(list_documents("val", ["2-5.청구서"]), key=lambda d: (d["form_code"] != "16", d["doc_id"]))
    claims = {f"{d['doc_id']} · {'신양식' if d['form_code'] == '16' else '구양식(위임 판단 불가)'}": d for d in ordered}
    powers = {d["doc_id"]: d for d in list_documents("val", ["2-3.위임장"])}
    return claims, powers


def resubmission_view():
    """보완대기 건에 고객이 빠진 서류를 추가로 낸다."""
    conn = get_conn()
    waiting = list_claims(conn, status="보완대기")
    if not waiting:
        st.info("보완을 기다리는 청구 건이 없습니다.")
        return
    labels = {f"{c['case_id']} · {c['claim']['type']} · {len(c['rounds'])}회차": c["case_id"] for c in waiting}
    case_id = labels[st.selectbox("보완 대기 건", list(labels), key="resubmit_case")]
    bundle = get_claim(conn, case_id)
    if bundle["customer_message"]:
        st.markdown("**고객에게 보낸 보완 안내**")
        st.code(bundle["customer_message"], language=None)

    claims, powers = sample_documents()
    left, right = st.columns(2)
    with left:
        claim_label = st.selectbox("고쳐서 다시 낸 보험금청구서 (없으면 그대로 둠)", ["(없음)"] + list(claims),
                                   key="resubmit_claim_doc")
        power_label = st.selectbox("새로 낸 위임장", ["(없음)"] + list(powers), key="resubmit_power_doc")
    with right:
        still_missing = [m["any_of"][0] for m in bundle["missing"] if m["name"] not in ("보험금청구서", "위임장")]
        others = st.multiselect("추가로 낸 서류 (종류만 선택)",
                                [d for d in document_catalog() if d not in ("보험금청구서", "위임장")],
                                default=still_missing, key="resubmit_others")
    if st.button("보완 서류 제출", type="primary"):
        documents = [{"declared_type": d, "image": None} for d in others]
        if claim_label != "(없음)":
            documents.insert(0, {"declared_type": "보험금청구서", "image": load_image(claims[claim_label])})
        if power_label != "(없음)":
            documents.insert(0, {"declared_type": "위임장", "image": load_image(powers[power_label])})
        with st.spinner("추가 서류를 붙여 다시 판단하는 중..."):
            updated = resubmit_claim(conn, case_id, documents)
            save_entry_images(updated["documents"][-len(documents):], [d["image"] for d in documents])
        last = updated["rounds"][-1]
        st.subheader(f"{last['round']}회차 결정: {decision_badge(updated['decision'])}")
        if last["resolved"]:
            st.success("해결된 서류: " + ", ".join(last["resolved"]))
        if last["still_missing"]:
            st.warning("아직 빠진 서류: " + ", ".join(last["still_missing"]))
        if updated["status"] == "검토대기":
            st.info("담당자 확인이 필요해 '청구 검토' 화면으로 넘어갔습니다.")
        st.dataframe([{"회차": r["round"], "시각": r["at"], "낸 서류": ", ".join(r["submitted"]), "결정": r["decision"],
                       "해결": ", ".join(r["resolved"]), "남은 누락": ", ".join(r["still_missing"])}
                      for r in updated["rounds"]], hide_index=True, width="stretch")


mode = st.radio("접수 구분", ["새 청구", "보완 서류 제출"], horizontal=True, key="mode")
if mode == "보완 서류 제출":
    resubmission_view()
    st.stop()

left, right = st.columns(2)
with left:
    st.subheader("1. 청구 정보")
    claim_type = st.radio("청구 유형", ["질병", "상해"], horizontal=True, key="claim_type")
    items = st.multiselect("청구 항목", list(CLAIM_ITEMS), default=["실손_통원"], format_func=CLAIM_ITEMS.get,
                           key="claim_items")
    injury_cause = None
    if claim_type == "상해":
        injury_cause = st.selectbox("사고 원인", list(INJURY_CAUSES), key="injury_cause",
                                    format_func=lambda c: "사고확인서류 발급 불가" if c == "발급불가" else c)
    under_50 = "실손_입원" in items and st.checkbox("입원 진료비 50만원 이하", key="under_50")
    manual = any(i.startswith("실손") for i in items) and st.checkbox("비급여 항목 또는 도수치료 있음", key="manual")
    delegation = st.checkbox("타인에게 보험금 위임", key="delegation")
    family = st.checkbox("가족관계 확인 필요 (배우자·자녀 보장, 수익자 미성년)", key="family")
    no_beneficiary = "사망" in items and st.checkbox("수익자 미지정", key="no_beneficiary")
    claim = {"type": claim_type, "items": items, "inpatient_under_50": bool(under_50),
             "noncovered_or_manual": bool(manual), "injury_cause": injury_cause, "delegation": delegation,
             "family_check": family, "beneficiary_unspecified": bool(no_beneficiary)}

with right:
    st.subheader("2. 서류 묶음")
    claims, powers = sample_documents()
    claim_id = st.selectbox("보험금청구서 이미지 (검증 데이터)", ["(없음)"] + list(claims), index=1, key="claim_doc")
    power_id = st.selectbox("위임장 이미지 (검증 데이터)", ["(없음)"] + list(powers), key="power_doc")
    uploaded = st.file_uploader("또는 청구서·위임장 이미지 올리기 (양식은 자동 판별)", type=["png", "jpg", "jpeg"],
                                accept_multiple_files=True, key="uploads")
    other_docs = st.multiselect("함께 제출한 다른 서류 (종류만 선택)",
                                [d for d in document_catalog() if d not in ("보험금청구서", "위임장")],
                                default=["개인(신용)정보처리동의서", "신분증 사본", "진료비계산영수증"], key="other_docs")
    engine = st.radio("추출 엔진", list(ENGINE_NAMES), format_func=ENGINE_NAMES.get, horizontal=True, key="engine")

# 제출 전 미리보기: 지금 선택한 서류로 무엇이 빠졌는지
declared = set(other_docs)
if claim_id != "(없음)":
    declared.add("보험금청구서")
if power_id != "(없음)":
    declared.add("위임장")
preview = check_completeness(required_documents(claim), declared | ({"보험금청구서"} if uploaded else set()))
st.subheader("3. 제출 전 점검")
if preview:
    st.warning("지금 선택한 서류로는 아래 서류가 빠져 있습니다 (청구서 내용 확인 전 기준):  \n"
               + "  \n".join(f"- {m['name']} ({m['issuer']})" for m in preview))
else:
    st.success("청구 정보 기준 필요 서류가 모두 선택됐습니다.")

if st.button("청구 접수", type="primary"):
    documents = [{"declared_type": d, "image": None} for d in other_docs]
    if claim_id != "(없음)":
        documents.insert(0, {"declared_type": "보험금청구서", "image": load_image(claims[claim_id])})
    if power_id != "(없음)":
        documents.insert(1, {"declared_type": "위임장", "image": load_image(powers[power_id])})
    for file in uploaded or []:
        documents.append({"declared_type": "보험금청구서", "image": Image.open(file).convert("RGB")})
    with st.spinner("서류를 판별하고 읽는 중..."):
        st.session_state["bundle"] = process_claim(claim, documents, engine=engine, conn=get_conn())
        st.session_state["bundle_images"] = [d["image"] for d in documents]
        # 담당자 검토 화면에서 원본을 보여주려고 이미지를 저장한다
        save_entry_images(st.session_state["bundle"]["documents"], st.session_state["bundle_images"])

bundle = st.session_state.get("bundle")
if bundle:
    st.divider()
    st.subheader(f"결정: {decision_badge(bundle['decision'])}")
    st.caption(f"건 ID {bundle['case_id']}" + (" — '청구 검토' 화면에서 담당자가 확인합니다" if bundle["status"] == "검토대기" else ""))
    submitted = {d["classified_type"] or d["declared_type"] for d in bundle["documents"]}
    st.markdown("**구비서류 체크리스트**")
    st.dataframe([{
        "제출": "✓" if any(x in submitted for x in r["any_of"]) else "✗",
        "서류": r["name"], "대체 가능": ", ".join(r["any_of"]) if len(r["any_of"]) > 1 else "",
        "필요 이유": r["reason"], "근거": "질병 안내" if r["source"].endswith("1301.shtm") else "상해 안내",
    } for r in bundle["requirements"]], hide_index=True, width="stretch")
    if bundle["checks"]:
        st.markdown("**서류 간 대조**")
        st.dataframe([{"규칙": c["rule"], "결과": STATUS_LABELS[c["status"]], "내용": c["message"]}
                      for c in bundle["checks"]], hide_index=True, width="stretch")
    if bundle["customer_message"]:
        st.markdown("**고객 보완 안내문 (자동 작성)**")
        st.code(bundle["customer_message"], language=None)
    with st.expander(f"판단 사유 전체 ({len(bundle['reasons'])}건)"):
        for reason in bundle["reasons"]:
            st.write("- " + reason)
    for document, image in zip(bundle["documents"], st.session_state["bundle_images"]):
        if image is None:
            continue
        with st.expander(f"{document['declared_type']} → 판별: {document['classified_type'] or '미분류'}"):
            if document["extracted"]:
                st.image(draw_fields(image, document["form_code"], document["extracted"]), width=500)
                st.dataframe([{"칸": k, "값": v["value"], "확신도": v["score"]} for k, v in document["extracted"].items()],
                             hide_index=True, width="stretch")
            if document["rules"]:
                st.dataframe(rules_table(document["rules"]), hide_index=True, width="stretch")
