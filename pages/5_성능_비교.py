"""화면 5: 성능 비교 — results/ 폴더의 평가 결과를 보여준다."""
import csv
import json

import streamlit as st

from src.ui_common import RESULTS_DIR

st.set_page_config(page_title="성능 비교", layout="wide")
st.title("성능 비교")


def read_csv(name):
    path = RESULTS_DIR / name
    if not path.exists():
        return None
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


classify_rows = read_csv("eval_classify.csv")
if classify_rows:
    total = sum(int(r["count"]) for r in classify_rows)
    correct = sum(int(r["count"]) for r in classify_rows if r["truth"] == r["predicted"])
    st.metric("서류 분류 정확도 (검증 8종)", f"{correct / total:.1%}", help=f"{correct}/{total}장")

st.header("정답 라벨 보정")
unlabeled = read_csv("ground_truth_unlabeled.csv")
if unlabeled:
    by_form = {}
    for row in unlabeled:
        form = by_form.setdefault(row["form_code"], {"labeled": 0, "unlabeled": 0, "blank": 0})
        for key in form:
            form[key] += int(row[key])
    names = {"12": "위임장", "15": "청구서(구)", "16": "청구서(신)"}
    st.dataframe([{"양식": names.get(code, code), "라벨 있음": v["labeled"], "글씨 있는데 라벨 없음": v["unlabeled"],
                   "진짜 빈칸": v["blank"]} for code, v in by_form.items()], hide_index=True, width="stretch")
    st.caption("AI Hub 라벨에는 손글씨가 있는데 박스가 없는 칸이 있습니다. 이런 칸을 '빈칸 정답'으로 채점하면 엔진이 맞게 읽어도 "
               "오답이 되므로, 칸 안의 잉크로 찾아 평가에서 뺐습니다 (scripts.build_ink).")

st.header("엔진 비교 (같은 청구서 100장)")
compare = read_csv("eval_engine_compare.csv")
if compare:
    st.dataframe(compare, hide_index=True, width="stretch")
    fields = read_csv("eval_engine_compare_fields.csv")
    if fields:
        chart = {}
        for row in fields:
            chart.setdefault(row["field"], {})[row["engine"]] = float(row["exact_rate"])
        st.bar_chart(chart, horizontal=True, height=900)
else:
    st.info("엔진 비교 결과가 아직 없습니다 (scripts.run_eval compare).")

st.header("엔진 A 전체 (청구서 400장)")
summary = read_csv("eval_summary.csv")
if summary:
    st.dataframe(summary, hide_index=True, width="stretch")

st.header("OCR 오류가 처리 결정에 주는 영향")
for engine, suffix in [("엔진 A", ""), ("엔진 B", "_claude")]:
    decisions = read_csv(f"eval_decisions{suffix}.csv")
    rules = read_csv(f"eval_rules{suffix}.csv")
    if decisions:
        st.subheader(engine)
        for row in decisions:
            for key in ["false_customer_rules", "truth_decisions", "rule_only_decisions", "with_conf_decisions"]:
                row[key] = ", ".join(f"{k} {v}" for k, v in json.loads(row[key]).items())
        st.dataframe(decisions, hide_index=True, width="stretch")
        st.caption("false_customer_docs: 정답으로는 통과인 규칙이 고객 보완요청 항목에 들어간 서류 수. "
                   "'잉크 판단'은 글씨가 있는데 읽지 못한 칸을 누락이 아니라 담당자 확인(R12)으로 보낸 결과입니다.")
    if rules:
        st.dataframe(rules, hide_index=True, width="stretch")

st.header("청구 건 단위 처리 (위임장 대조·위임 서류 자동 판단)")
bundle_rows = read_csv("eval_bundle.csv")
if bundle_rows:
    st.dataframe(bundle_rows, hide_index=True, width="stretch")
    st.caption("거짓 불일치: 내용이 일치하는 청구서·위임장 쌍인데 OCR 오류로 '불일치'가 나온 비율. "
               "그래서 서류 간 불일치는 고객에게 바로 보내지 않고 담당자가 원본을 확인합니다.")

st.caption("데이터 값이 무작위라 거의 모든 서류가 여러 규칙을 위반합니다. 결정 일치율보다 규칙별 일치율이 더 정직한 지표입니다.")
