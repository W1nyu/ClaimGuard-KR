# 청구 건 단위 처리: 구비서류 완비 판단 + 청구서·위임장 대조 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서류 한 장 단위였던 접수를 "청구 건"(청구 정보 + 서류 묶음) 단위로 바꿔, DB손해보험이 공개한 필요서류 안내를 기준으로 서류 완비 여부를 자동 판단하고 청구서와 위임장 내용을 대조한다.

**Architecture:** `src/claim_docs.py`에 DB손보 필요서류 안내(질병·상해, 2026.9.23 확인)를 규칙표로 옮기고, 청구 정보(유형·항목·조건)로 필요 서류 목록(대체 가능 서류 포함)을 만든다. `src/bundle.py`가 서류 묶음을 받아 이미지 서류는 기존 파이프라인으로 분류·추출하고, 의료기관·관공서 서류는 고객이 고른 서류 종류로 받는다. 청구서 값(예금주 ≠ 피보험자)이 위임 서류를 자동으로 필요 목록에 넣고, 위임장이 있으면 청구서와 대조한다. 결과는 서류 완비 판단 + 기존 처리 결정을 합친 건 단위 결정이다.

**Tech Stack:** 기존과 동일 (Python 3.10, PaddleOCR, SQLite, Streamlit, pytest)

## Global Constraints

- 범위: 장기보험 질병·상해 청구. 자동차보험·재물보험 제외.
- 규칙 출처: DB손해보험 홈페이지 보험금청구서류 안내 — 질병 `FWCUSV1301`, 상해 `FWCUSV1300` (2026.9.23 원문 확인). 규칙마다 출처 페이지를 코드에 적는다.
- 공개 데이터에 이미지가 있는 서류는 보험금청구서(15·16)와 위임장(12)뿐. 나머지 서류는 고객이 고른 서류 종류로만 처리하고 내용은 읽지 않는다 (화면·문서에 명시).
- 로컬 OCR 정확도를 올리는 작업은 하지 않는다. 모델 학습 없음. Claude API 호출 금지.
- 함수 위주, 한국어 주석, TDD, 작은 커밋.

## Task 1: 위임장 칸 위치와 정답
- [ ] `CATEGORY_BY_FORM` 추가, `draft_templates`를 양식 코드로 일반화 (완료: 칸 후보 20개, 잡음 24/30,863)
- [ ] `config/form_fields_12.json` 작성 (칸: 위임사항_피보험자, 사고_년·월·일, 보험상품명, 증권번호, 계약자명, 피보험자명, 작성_년·월·일, 위임인_성명·주민번호·연락처, 수임인_성명·주민번호·연락처·관계·은행명·계좌번호)
- [ ] 엔진 A 숫자 칸 보정 목록과 엔진 B 칸 설명에 위임장 칸 추가
- [ ] `build_ground_truth`를 양식 12까지 확장, 배정 실패율 확인

## Task 2: 구비서류 규칙표 `src/claim_docs.py`
**Produces:** `DOC_TYPES`(서류 종류 → 발급처), `CLAIM_ITEMS`, `required_documents(claim) -> list[Requirement]` (Requirement: `name`, `any_of: list[str]`, `reason`, `source`), `check_completeness(requirements, submitted: set[str]) -> list[missing]`
- [ ] 테스트: 공통 3종, 50만원 이하 입원 대체서류, 통원 진단명 서류, 도수치료 세부내역서, 상해 사고 입증(교통·산재·기타·발급불가), 위임 3종, 가족관계, 사망 수익자 미지정, 중복 서류는 한 번만
- [ ] 구현 → 통과 → commit

## Task 3: 청구 건 처리 `src/bundle.py`
**Produces:** `process_claim(claim, documents, engine, ...) -> dict` — 각 이미지 서류 처리 결과, 필요 서류, 누락 서류(발급처 포함), 대조 결과, 건 단위 결정·사유·고객 안내문
- 대조 규칙: B01 위임 필요(예금주 ≠ 피보험자)인데 위임 미선택 → 위임 서류 자동 추가, B02 위임장 수임인 = 청구서 예금주, B03 위임장 계좌·은행 = 청구서 계좌·은행, B04 위임장 피보험자 = 청구서 피보험자, B05 위임장 사고일 = 청구서 사고일, B06 제출 서류 종류와 분류 결과 불일치
- 건 결정: 서류 누락·대조 불일치 → 보완요청 (안내문에 서류명·발급처), 개별 서류 담당자검토 사유 → 담당자검토
- [ ] 테스트(가짜 추출기·분류기) → 구현 → 통과 → commit

## Task 4: 저장·화면·평가
- [ ] 감사 로그에 청구 건 기록 (cases 재사용: case_id = 건 ID, 서류별 결과는 JSON)
- [ ] 화면 `pages/0_청구_접수.py`: 청구 정보 입력 → 서류 묶음(검증 데이터 선택/업로드 + 서류 종류 선택) → 필요 서류 체크리스트, 누락·대조 결과, 결정
- [ ] 평가 스크립트: 가상 청구 건 N개(예금주≠피보험자 비율은 데이터 그대로)에서 위임 서류 자동 감지율, 청구서·위임장 대조 결과를 정답 값과 OCR 값으로 비교
- [ ] README·웹페이지 갱신 → commit
