# 4주차: 엔진 B(Claude CLI) + 감사 로그 + Streamlit 화면 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 구독 기반 Claude CLI를 엔진 B로 붙여 엔진 A와 같은 100장에서 비교하고, 처리 이력을 SQLite에 남기며, 서류 접수·검토 대기함·성능 비교·감사 로그 화면을 만든다.

**Architecture:** `extract_claude.py`가 양식 영역을 잘라 긴 변 1600px로 줄인 이미지를 임시 파일로 저장하고 `claude -p`(Read 도구만 허용)를 호출해 JSON 답을 파싱한다(실행 함수는 주입 가능 → 테스트에서 가짜 사용). `pipeline.py`가 분류→추출→검증→결정→기록을 한 함수로 묶고, `audit.py`가 서류 건·결정·수정 이력을 SQLite에 저장한다. Streamlit 페이지는 이 두 모듈만 호출한다.

**Tech Stack:** Python 3.10, Claude Code CLI 2.1.280 (`claude -p`), sqlite3(표준), streamlit 1.64 (`streamlit.testing.v1.AppTest`로 화면 테스트)

## Global Constraints

- Claude **API 호출 금지**. 엔진 B는 로컬 `claude` CLI(구독)만 사용. CLI가 없거나 실패·60초 초과 시 엔진 A로 대체하고 화면·로그에 표시.
- 함수 위주, 클래스 없음, 한국어 주석. `.venv/Scripts/python`, 프로젝트 최상위에서 실행.
- `data/`, `.env` git 제외. `results/` 집계 git 포함.
- 엔진 B 입력은 사람이 먼저 보지 않는다(정답 편향 방지). 모든 서류에 같은 프롬프트.

## 설계서와 달라진 점

| 설계서 4.5 | 변경 | 이유 |
|---|---|---|
| 평가 100장은 Claude Code 세션에서 사람이 대화로 처리 | 평가도 `claude -p` CLI로 일괄 처리 | 같은 구독이면서 모든 서류에 동일 프롬프트 → 공정·재현 가능. 탐색 시 1장 11초, 5칸 모두 정답 |
| 확신도 없음 | 모델이 "불확실한 칸" 목록을 함께 답하게 해 0.5 / 0.95로 변환 | 확신도 기반 담당자 검토 규칙을 엔진 B에도 적용하고, 자기 보고 확신도의 신뢰성을 측정 |

## 파일 구조

| 파일 | 역할 |
|---|---|
| `src/extract_claude.py` | 칸 설명·프롬프트, 이미지 준비, 응답 파싱, CLI 호출 |
| `scripts/run_claude_batch.py` | 양식별 50장(정렬 후 앞 50장) 일괄 추출, 이어 하기 지원 |
| `scripts/run_eval.py` (수정) | `compare`: 같은 100장에서 엔진 A·B 비교 + 불확실 표시 신뢰성 |
| `scripts/run_decision_eval.py` (수정) | 엔진 인자 추가 (`paddle` / `claude`) |
| `src/audit.py` | SQLite: cases, decisions, edits |
| `src/pipeline.py` | 서류 1건 처리 (분류→추출→검증→결정→기록), 담당자 수정 반영 |
| `app.py`, `pages/1_서류_접수.py`, `pages/2_검토_대기함.py`, `pages/3_성능_비교.py`, `pages/5_감사_로그.py` | 화면 |
| `tests/test_extract_claude.py`, `tests/test_audit.py`, `tests/test_pipeline.py`, `tests/test_app.py` | 테스트 |

---

### Task 1: 엔진 B (`extract_claude.py`)
**Produces:** `FIELD_GUIDE: dict[str, dict[str, str]]`(양식→칸→설명), `CROP_BOX: dict[str, tuple]`, `build_prompt(form_code, image_path) -> str`, `prepare_image(image, form_code) -> PIL.Image`, `parse_response(text, form_code) -> dict[칸, {"value","raw","score"}]`(JSON 못 찾으면 `ValueError`), `extract_fields_cli(image, form_code, runner=None, timeout=60) -> dict` (runner: `(prompt) -> str`; 기본은 subprocess로 `claude -p <prompt> --allowedTools Read --output-format text`)
- [ ] 테스트 작성(프롬프트에 모든 칸·"고치지 말 것" 포함, 코드블록 JSON 파싱, 누락 칸은 빈칸 score 0.95, 불확실 칸 0.5, 숫자 칸 clean_value 적용, 가짜 runner로 CLI 경로) → 실패 확인 → 구현 → 통과 → commit

### Task 2: 일괄 추출 (`run_claude_batch.py`)
- [ ] 스크립트 작성: 양식 15·16 검증 데이터 앞 50장씩, 응답 원문을 `data/processed/claude_outputs/{doc_id}.txt`에 저장(있으면 건너뜀), 걸린 초 기록, 끝나면 `predictions/claude_val_{code}.jsonl` 생성
- [ ] 백그라운드 실행 (약 20분) → commit

### Task 3: 엔진 비교 평가
- [ ] `run_eval.py compare`: 두 엔진의 같은 100장 칸 완전 일치율·CER·장당 초·불확실 표시 칸 정확도 → `results/eval_engine_compare.csv`, `results/eval_engine_compare_fields.csv`
- [ ] `run_decision_eval.py claude`: 엔진 B 결정 일치율 → `results/eval_decisions_claude.csv`, `results/eval_rules_claude.csv`
- [ ] 실행 → commit

### Task 4: 감사 로그·파이프라인 (`audit.py`, `pipeline.py`)
**Produces (audit):** `connect(path=AUDIT_DB) -> sqlite3.Connection`(테이블 생성 포함), `save_case(conn, case) -> None`, `get_case(conn, case_id) -> dict|None`, `list_cases(conn, status=None) -> list[dict]`, `log_decision(conn, case_id, actor, engine, decision, reasons)`, `log_edit(conn, case_id, field, old, new, editor)`, `list_decisions(conn, case_id=None)`, `list_edits(conn, case_id=None)`
**Produces (pipeline):** `process_document(image, engine="paddle", case_id=None, conn=None, extractors=None, classifier=None, today=None, refs=None) -> dict case` (`case` 키: `case_id, form_code, engine, engine_note, extracted, values, rules, decision, status`), `apply_edits(conn, case_id, new_values, editor, today=None, refs=None) -> dict case`, `approve(conn, case_id, editor)`
- [ ] 테스트(가짜 추출기·분류기·refs, 임시 DB) → 실패 확인 → 구현 → 통과 → commit

### Task 5: Streamlit 화면
- [ ] `app.py`(소개·메뉴), 페이지 1(검증 서류 선택/업로드 → 엔진 선택 → 처리 결과·사유·안내문·이미지 위 칸 표시), 2(담당자검토 건 목록 → 값 수정·재검증 → 승인), 3(`results/*.csv` 표·막대그래프), 5(결정·수정 이력 표)
- [ ] `tests/test_app.py`: AppTest로 각 페이지가 오류 없이 뜨는지
- [ ] `streamlit run app.py` 실제 실행 확인 → commit
