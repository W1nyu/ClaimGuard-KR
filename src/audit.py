"""감사 로그: 서류 건, 결정 이력, 수정 이력을 SQLite 파일 하나에 남긴다.

누가(AI 또는 담당자) 언제 어떤 결정을 했고 어떤 값을 바꿨는지 나중에 확인할 수 있게 하는 것이 목적이다
(금융분야 AI 가이드라인의 사후 점검·책임 투명성).
"""
import json
import sqlite3
from datetime import datetime

from src.load_data import PROJECT_ROOT

AUDIT_DB = PROJECT_ROOT / "data" / "processed" / "audit.db"

# JSON 문자열로 저장하는 칸
JSON_COLUMNS = ["extracted", "values", "rules", "reasons", "low_confidence_fields"]
CASE_COLUMNS = ["case_id", "created_at", "form_code", "engine", "engine_note", "extracted", "values", "rules",
                "decision", "reasons", "customer_message", "low_confidence_fields", "status"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY, created_at TEXT, form_code TEXT, engine TEXT, engine_note TEXT,
    extracted TEXT, "values" TEXT, rules TEXT, decision TEXT, reasons TEXT, customer_message TEXT,
    low_confidence_fields TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, at TEXT, actor TEXT, engine TEXT, decision TEXT, reasons TEXT
);
CREATE TABLE IF NOT EXISTS claims (
    case_id TEXT PRIMARY KEY, created_at TEXT, decision TEXT, status TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, at TEXT, field TEXT, old TEXT, new TEXT, editor TEXT
);
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def connect(path=AUDIT_DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Streamlit은 여러 스레드에서 같은 연결을 쓸 수 있어 check_same_thread를 끈다
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _row_to_case(row):
    case = dict(row)
    for column in JSON_COLUMNS:
        case[column] = json.loads(case[column]) if case[column] else None
    return case


def save_case(conn, case):
    """같은 case_id가 있으면 덮어쓴다 (최초 생성 시각은 유지)."""
    existing = get_case(conn, case["case_id"])
    row = dict(case)
    row["created_at"] = existing["created_at"] if existing else _now()
    values = [json.dumps(row.get(c), ensure_ascii=False) if c in JSON_COLUMNS else row.get(c) for c in CASE_COLUMNS]
    columns = ", ".join(f'"{c}"' for c in CASE_COLUMNS)
    conn.execute(f"INSERT OR REPLACE INTO cases ({columns}) VALUES ({', '.join('?' * len(CASE_COLUMNS))})", values)
    conn.commit()


def get_case(conn, case_id):
    row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return _row_to_case(row) if row else None


def list_cases(conn, status=None):
    if status:
        rows = conn.execute("SELECT * FROM cases WHERE status = ? ORDER BY created_at", (status,))
    else:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at")
    return [_row_to_case(r) for r in rows.fetchall()]


def log_decision(conn, case_id, actor, engine, decision, reasons):
    conn.execute(
        "INSERT INTO decisions (case_id, at, actor, engine, decision, reasons) VALUES (?, ?, ?, ?, ?, ?)",
        (case_id, _now(), actor, engine, decision, json.dumps(reasons, ensure_ascii=False)),
    )
    conn.commit()


def log_edit(conn, case_id, field, old, new, editor):
    conn.execute(
        "INSERT INTO edits (case_id, at, field, old, new, editor) VALUES (?, ?, ?, ?, ?, ?)",
        (case_id, _now(), field, old, new, editor),
    )
    conn.commit()


def list_decisions(conn, case_id=None):
    query, params = "SELECT * FROM decisions", ()
    if case_id:
        query, params = query + " WHERE case_id = ?", (case_id,)
    rows = [dict(r) for r in conn.execute(query + " ORDER BY id", params).fetchall()]
    for row in rows:
        row["reasons"] = json.loads(row["reasons"])
    return rows


def list_edits(conn, case_id=None):
    query, params = "SELECT * FROM edits", ()
    if case_id:
        query, params = query + " WHERE case_id = ?", (case_id,)
    return [dict(r) for r in conn.execute(query + " ORDER BY id", params).fetchall()]


def save_claim(conn, bundle):
    """청구 건(서류 묶음) 결과를 통째로 JSON으로 저장한다. 같은 건 ID면 덮어쓴다."""
    existing = get_claim(conn, bundle["case_id"])
    created = existing["created_at"] if existing else _now()
    # 이미지 객체는 저장하지 않는다
    data = json.dumps({**bundle, "created_at": created}, ensure_ascii=False, default=str)
    conn.execute("INSERT OR REPLACE INTO claims (case_id, created_at, decision, status, data) VALUES (?, ?, ?, ?, ?)",
                 (bundle["case_id"], created, bundle["decision"], bundle["status"], data))
    conn.commit()


def get_claim(conn, case_id):
    row = conn.execute("SELECT data FROM claims WHERE case_id = ?", (case_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_claims(conn, status=None):
    query, params = "SELECT data FROM claims", ()
    if status:
        query, params = query + " WHERE status = ?", (status,)
    return [json.loads(r["data"]) for r in conn.execute(query + " ORDER BY created_at", params).fetchall()]
