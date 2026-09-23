# 5주차: AI 위험평가(H) + 결과 정리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 금융분야 AI 가이드라인(2026.6) 예시 위험평가 체계로 이 시스템을 두 시나리오(엔진 A 로컬 / 엔진 B 외부 모델)로 평가하는 모듈·화면을 만들고, 프로젝트 전체 결과를 README와 포트폴리오 문서로 정리한다.

**Architecture:** `risk_assessment.py`에 가이드라인 15쪽 예시표(16개 항목, 총 100점)를 상수로 두고, 항목별 경감 수행률(0~1)을 받아 잔여 위험 = 배점 × (1 − 수행률), 총점, 등급(25/50/75 기준), 필요 통제를 계산한다. 두 시나리오의 수행률과 근거 문장은 이 프로젝트의 실제 측정 결과를 인용한다. 화면 4는 슬라이더로 수행률을 바꿔 보며 보고서(Markdown)를 내려받는다.

**Tech Stack:** Python 3.10, streamlit, pytest

## Global Constraints

- 함수 위주, 한국어 주석, `.venv/Scripts/python`, 프로젝트 최상위에서 실행.
- 배점·등급 기준은 가이드라인 원문 그대로 (본문 13~14쪽 방법, 15쪽 예시표). 원문 쪽수를 주석에 단다.
- 시나리오 수행률은 평가자(본인)의 판단임을 화면·보고서에 명시하고, 항목마다 근거를 적는다.
- 결과 문서의 수치는 `results/*.csv`와 일치해야 한다.

## Task 1: `src/risk_assessment.py`
**Produces:** `ITEMS: list[dict]`(principle, item, points), `grade(total) -> str`, `assess(rates: dict[str, float]) -> dict`(items, by_principle, total, grade, committee_review), `required_controls(grade) -> list[str]`, `SCENARIOS: dict[name, dict[item, (rate, evidence)]]`, `report_markdown(name, result, evidence) -> str`
- [ ] 테스트: 배점 합 100·원칙별 20/30/20/30, 원문 예시(경감 점수) → 총 54점·고위험, 등급 경계 24.9/25/49.9/50/75, 수행률 범위 밖 오류, 두 시나리오 모든 항목 포함·엔진 B 총점이 더 높음, 보고서에 등급·근거 포함
- [ ] 구현 → 통과 → commit

## Task 2: 화면 4 `pages/4_AI_위험평가.py`
- [ ] 시나리오 선택 → 항목별 슬라이더(기본값=시나리오) → 총점·등급·원칙별 막대·필요 통제·근거 표 → 보고서 내려받기, 두 시나리오 비교표
- [ ] AppTest 목록에 추가 → 통과 → commit

## Task 3: 결과 정리
- [ ] `README.md`: 문제, 구조, 실행 방법, 결과표, 한계
- [ ] `docs/포트폴리오.md`: 배경→접근→결과→배운 점, 예상 면접 질문과 답
- [ ] 수치가 results CSV와 일치하는지 대조 → commit
