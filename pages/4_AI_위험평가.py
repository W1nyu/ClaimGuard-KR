"""화면 4: AI 위험평가 — 금융분야 인공지능 가이드라인(2026.6) 예시 체계로 이 시스템을 평가한다."""
import streamlit as st

from src.risk_assessment import ITEMS, IMPLEMENTED, SCENARIOS, assess, report_markdown, required_controls

st.set_page_config(page_title="AI 위험평가", layout="wide")
st.title("AI 위험평가")
st.caption(
    "금융분야 인공지능 가이드라인(2026.6) 15쪽 예시표: 16개 항목, 총 100점. "
    "잔여 위험 = 배점 × (1 − 경감 수행률). 25점 미만 저위험 · 50점 미만 중위험 · 50점 이상 고위험 · 75점 이상 의사결정기구 재검토. "
    "수행률은 평가자(작성자) 판단이며 근거는 이 프로젝트의 측정 결과입니다."
)

# 두 시나리오 비교
comparison = []
for name, scenario in SCENARIOS.items():
    result = assess({item: rate for item, (rate, _) in scenario.items()})
    comparison.append({"시나리오": name, "총 잔여 위험": round(result["total"], 1), "등급": result["grade"],
                       **{p: round(v, 1) for p, v in result["by_principle"].items()}})
st.subheader("시나리오 비교")
st.dataframe(comparison, hide_index=True, width="stretch")

st.subheader("직접 평가해 보기")
name = st.selectbox("시작 시나리오", list(SCENARIOS))
scenario = SCENARIOS[name]
rates, evidence = {}, {}
columns = st.columns(2)
for index, item in enumerate(ITEMS):
    default_rate, text = scenario[item["item"]]
    with columns[index % 2]:
        rates[item["item"]] = st.slider(
            f"[{item['principle']}] {item['item']} (배점 {item['points']})", 0.0, 1.0, default_rate, 0.1,
            help=text, key=f"{name}_{item['item']}",
        )
    evidence[item["item"]] = text

result = assess(rates)
first, second, third = st.columns(3)
first.metric("총 잔여 위험", f"{result['total']:.1f}점")
second.metric("등급", result["grade"])
third.metric("의사결정기구 재검토", "대상" if result["committee_review"] else "아님")
st.bar_chart({p: v for p, v in result["by_principle"].items()}, horizontal=True)

st.subheader(f"필요 통제 ({result['grade']})")
st.dataframe([{"통제": c, "이 시스템의 구현": IMPLEMENTED[c]} for c in required_controls(result["grade"])],
             hide_index=True, width="stretch")

st.subheader("항목별 근거")
st.dataframe([{"원칙": r["principle"], "항목": r["item"], "배점": r["points"], "수행률": r["rate"],
               "잔여 위험": round(r["residual"], 1), "근거": evidence[r["item"]]} for r in result["items"]],
             hide_index=True, width="stretch")

st.download_button("보고서 내려받기 (Markdown)", report_markdown(name, result, evidence),
                   file_name="ai_risk_report.md", mime="text/markdown")
