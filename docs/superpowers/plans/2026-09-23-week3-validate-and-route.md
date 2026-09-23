# 3주차: 기준 데이터 조회 + 접수 검증(R01~R11) + 처리 결정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 추출된 청구서 값을 기준 데이터(KCD-9, KSCO 8차, 은행 목록, 도로명주소)와 규칙으로 검증하고, 자동접수 / 보완요청 / 담당자검토를 결정한 뒤, OCR 오류가 결정을 얼마나 바꾸는지(결정 일치율) 측정한다.

**Architecture:** `reference.py`가 원본 파일을 한 번 읽어 JSON 캐시로 저장하고 이름 조회(정확 → 부분 → 유사)와 주소 API 조회(캐시·실패 시 확인불가)를 제공한다. `validate.py`는 칸 값 dict를 받아 규칙 결과 목록을 돌려주며, 기준 데이터 조회 함수는 `refs` 인자로 바꿔 끼울 수 있어 테스트가 파일·네트워크 없이 돈다. `route.py`는 규칙 결과와 칸 확신도로 처리 결정·사유·고객 안내문을 만든다.

**Tech Stack:** Python 3.10, openpyxl, pypdf, 표준 라이브러리(urllib, difflib, datetime, re), pytest

## Global Constraints

- 실행은 `.venv/Scripts/python`, 프로젝트 최상위에서.
- 함수 위주, 클래스 없음, 한국어 주석.
- `data/`, `.env`는 git 제외. `results/` 집계는 git 포함.
- API 키는 `.env`의 `API1`(도로명주소)에서 읽고 출력·로그에 남기지 않는다.
- 외부 조회 실패 시 앱이 멈추지 않고 `unknown`(확인불가) → 담당자검토.
- Claude API 호출 금지.

## 탐색 결과 (계획에 반영)

- KCD-9 시트 `KCD-9 DB Masterfile`: 4행부터 데이터, 열 2=코드, 5=한글명칭, 7=최하위코드 여부. 학습 진단명의 85.5%가 한글명칭과 정확 일치.
- KSCO PDF: 줄 앞 5자리 숫자 + 한글명 정규식으로 세세분류 1,265개 추출. 학습 직업값 정확 일치 14%, 부분 일치 31% (데이터 직업이 가상값).
- 은행: 금융회사코드 앞 3자리 기준 105개 이름. 데이터 은행명은 전부 가상 → R10은 거의 모두 위반이 정상.
- 도로명주소 API: 실제 주소는 조회되고 데이터의 가상 주소는 0건.
- 청구서(구) 15의 청구연도는 "20__"의 뒤 두 자리만 손글씨 → 2000 + 값.

## 규칙 표 (설계서 4.7 확정판)

| ID | 대상 양식 | 규칙 | 위반 시 |
|---|---|---|---|
| R01 | 15, 16 | 필수 칸 누락 | 보완요청 |
| R02 | 15, 16 | 사고일·작성일(청구일)이 실제 날짜이고 1900년~올해 | 보완요청 |
| R03 | 15, 16 | 사고일 ≤ 작성일 ≤ 오늘 | 보완요청 |
| R04 | 15, 16 | 작성일(없으면 오늘) 기준 사고일이 3년 초과 (상법 제662조) | 담당자검토 |
| R05 | 16 | 주민번호 13자리, 성별자리 1~8, 생년월일 실재 | 보완요청 |
| R06 | 15, 16 | 연락처(0으로 시작 9~11자리), 이메일 형식 | 보완요청 |
| R07 | 15, 16 | 주소 실재 (도로명주소 API). 조회 실패 시 확인불가 | 보완요청 / 확인불가는 담당자검토 |
| R08 | 16 | 진단명 KCD-9 정확 일치 (유사·실패는 후보 제시) | 담당자검토 |
| R09 | 16 | 직업 KSCO 정확 또는 부분 일치 | 담당자검토 |
| R10 | 16 | 은행명이 목록에 있음, 계좌번호 숫자 10~14자리 | 보완요청 |
| R11 | 16 | 예금주 ≠ 피보험자 → 위임장·인감증명서 | 추가서류 |

필수 칸 — 16: 피보험자_성명, 주민번호, 직업, 주소_시도, 연락처, 사고_년, 사고_월, 사고_일, 진단명, 계좌번호, 은행명, 예금주, 작성_년, 작성_월, 작성_일, 청구권자 / 15: 보험종목, 증권번호, 계약자, 사고일자, 사고원인, 사고경위, 청구_년, 청구_월, 청구_일, 청구인_성명, 주소_시도, 연락처

## 파일 구조

| 파일 | 역할 |
|---|---|
| `requirements.txt` (수정) | openpyxl, pypdf 추가 |
| `src/reference.py` | 기준표 캐시, 이름 조회, 은행 확인, 주소 조회, .env 읽기 |
| `src/validate.py` | 규칙 R01~R11 |
| `src/route.py` | 처리 결정, 사유, 고객 안내문 |
| `scripts/run_decision_eval.py` | 정답 값 vs 엔진 A 값의 규칙·결정 일치율 |
| `tests/test_reference.py`, `tests/test_validate.py`, `tests/test_route.py` | 테스트 |

---

### Task 1: 기준 데이터 조회 (`reference.py`)

**Interfaces — Produces:**
- `normalize_name(text) -> str`
- `load_env(path=PROJECT_ROOT/".env") -> dict[str, str]`
- `match_name(query, table, allow_contains=False) -> dict` — `{"match": "exact"|"contains"|"similar"|"none", "code": str|None, "name": str|None, "candidates": list[str]}`; `table`은 `{정규화 이름: [코드, 원래 이름]}`
- `kcd_table()`, `ksco_table()` → 위 형식 표, `bank_table()` → `{3자리 코드: 은행명}`
- `lookup_diagnosis(name) -> dict`, `lookup_job(name) -> dict` (match_name 결과)
- `is_known_bank(name, banks=None) -> bool`
- `check_address(address, key=None, fetch=None, cache_path=...) -> {"status": "found"|"not_found"|"unavailable", "road_addr": str|None}`

- [ ] Step 1: `tests/test_reference.py` 작성 (코드는 파일 참조: 정확·부분·유사·실패 매칭, 전각 정규화, 은행 "은행" 접미사, 주소 캐시·API 실패)
- [ ] Step 2: 실패 확인 `.venv/Scripts/python -m pytest tests/test_reference.py -q` → ModuleNotFoundError
- [ ] Step 3: `src/reference.py` 구현
- [ ] Step 4: 통과 확인 + 실제 기준표 캐시 생성: `.venv/Scripts/python -c "from src.reference import *; print(len(kcd_table()), len(ksco_table()), len(bank_table())); print(lookup_diagnosis('멀미'))"` → `T75.3`
- [ ] Step 5: Commit `feat: 기준 데이터 조회(KCD-9·KSCO·은행·도로명주소)`

### Task 2: 접수 검증 (`validate.py`)

**Interfaces — Produces:**
- `validate(form_code: str, values: dict[str, str], today: date | None = None, refs: dict | None = None) -> list[dict]` — 각 결과 `{"rule", "status": "pass"|"fail"|"unknown", "fields": list[str], "message": str, "action": "보완요청"|"담당자검토"|"추가서류", "detail": dict}`. 해당 없는 규칙은 목록에 없다.
- 상수 `SUPPLEMENT="보완요청"`, `REVIEW="담당자검토"`, `DOCUMENT="추가서류"`, `REQUIRED_FIELDS`
- `refs` 키: `diagnosis`, `job`, `bank`, `address` (Task 1 함수와 같은 시그니처)

- [ ] Step 1: `tests/test_validate.py` 작성 (규칙별 통과·위반, 가짜 refs 사용)
- [ ] Step 2: 실패 확인
- [ ] Step 3: `src/validate.py` 구현
- [ ] Step 4: 통과 확인
- [ ] Step 5: Commit `feat: 접수 검증 규칙 R01~R11`

### Task 3: 처리 결정 (`route.py`)

**Interfaces — Produces:**
- `decide(rule_results, extracted=None, threshold=0.85) -> dict` — `{"decision": "자동접수"|"보완요청"|"담당자검토", "reasons": list[str], "customer_message": str|None, "low_confidence_fields": list[str]}`. `extracted`는 엔진 출력 `{칸: {"value", "score"}}`; 값이 있고 확신도가 기준 미만인 칸이 하나라도 있으면 담당자검토.
- 우선순위: 담당자검토(검토 규칙 위반·확인불가·저확신 칸) > 보완요청(보완요청·추가서류 위반) > 자동접수

- [ ] Step 1: `tests/test_route.py` 작성
- [ ] Step 2: 실패 확인
- [ ] Step 3: `src/route.py` 구현
- [ ] Step 4: 통과 확인
- [ ] Step 5: Commit `feat: 처리 결정과 고객 보완 안내문`

### Task 4: 결정 일치율 평가 (`run_decision_eval.py`)

**Interfaces — Consumes:** 정답 JSONL(1주차), `paddle_val_{15,16}.jsonl`(2주차), `validate`, `decide`
**Produces:** `results/eval_rules.csv` (양식·규칙별 상태 일치율), `results/eval_decisions.csv` (양식별: 정답 결정 분포, 규칙만 쓴 결정 일치율, 확신도 포함 결정 분포, **잘못된 자동접수 건수**)

- [ ] Step 1: 스크립트 작성
- [ ] Step 2: 실행 `.venv/Scripts/python -m scripts.run_decision_eval` (주소 API 최대 약 800회, 캐시됨)
- [ ] Step 3: 전체 테스트 + Commit `feat: OCR 오류의 결정 영향(결정 일치율) 평가`

각 Task의 전체 코드는 해당 커밋의 파일과 같다(구현 후 아래 부록에 옮겨 적는다).
