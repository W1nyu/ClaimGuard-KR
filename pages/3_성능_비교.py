"""화면 3: 성능 비교 — results/ 폴더의 평가 결과를 보여준다."""
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
            for key in ["truth_decisions", "rule_only_decisions", "with_conf_decisions"]:
                row[key] = ", ".join(f"{k} {v}" for k, v in json.loads(row[key]).items())
        st.dataframe(decisions, hide_index=True, width="stretch")
    if rules:
        st.dataframe(rules, hide_index=True, width="stretch")

st.caption("데이터 값이 무작위라 거의 모든 서류가 여러 규칙을 위반합니다. 결정 일치율보다 규칙별 일치율이 더 정직한 지표입니다.")
