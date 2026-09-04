"""SQLite persistence layer (stdlib only, thread-safe, auto-seeding).

Production deployment uses Supabase Postgres (see infra/supabase/schema.sql);
this local store mirrors the same schema so the full stack runs offline
during the hackathon demo with zero external dependencies.
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from . import config

_write_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return "{}_{}".format(prefix, uuid.uuid4().hex[:12])


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def query(sql: str, params: Iterable = ()) -> list:
    with _write_lock:
        cur = get_conn().execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Iterable = ()) -> Optional[dict]:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable = ()) -> int:
    with _write_lock:
        conn = get_conn()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def executemany(sql: str, seq: Iterable[tuple]) -> None:
    with _write_lock:
        conn = get_conn()
        conn.executemany(sql, [tuple(s) for s in seq])
        conn.commit()


def jloads(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def jdumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('applicant','officer','admin','consultant')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS business_profiles (
    id TEXT PRIMARY KEY,
    owner_id TEXT UNIQUE NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    sector TEXT NOT NULL,
    district TEXT DEFAULT '',
    industrial_zone TEXT DEFAULT '',
    investment_size REAL DEFAULT 0,
    employee_count INTEGER DEFAULT 0,
    project_stage TEXT DEFAULT 'planning',
    authorized_person TEXT DEFAULT '',
    pan_enc TEXT DEFAULT '',
    pan_masked TEXT DEFAULT '',
    pan_hash TEXT DEFAULT '',
    gst_enc TEXT DEFAULT '',
    gst_masked TEXT DEFAULT '',
    gst_hash TEXT DEFAULT '',
    registration_no TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    sector TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    description TEXT DEFAULT '',
    sla_days INTEGER NOT NULL,
    required_documents TEXT NOT NULL,
    dependency_ids TEXT DEFAULT '[]',
    parallel_group TEXT DEFAULT '',
    condition_rule TEXT DEFAULT '',
    green_channel_eligible INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

SCHEMA_PART2 = """
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES business_profiles(id),
    approval_id TEXT NOT NULL REFERENCES approvals(id),
    status TEXT NOT NULL DEFAULT 'draft',
    submitted_at TEXT,
    sla_deadline TEXT,
    assigned_officer_id TEXT,
    decision_source TEXT,
    decision_notes TEXT DEFAULT '',
    decided_at TEXT,
    readiness_score REAL DEFAULT 0,
    readiness_breakdown TEXT DEFAULT '[]',
    green_channel INTEGER DEFAULT 0,
    provisional_certificate TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    business_id TEXT NOT NULL,
    type TEXT NOT NULL,
    label TEXT DEFAULT '',
    filename TEXT DEFAULT '',
    file_ref TEXT DEFAULT '',
    mime TEXT DEFAULT '',
    size INTEGER DEFAULT 0,
    extracted_fields TEXT DEFAULT '{}',
    validation_flags TEXT DEFAULT '[]',
    checks_passed INTEGER DEFAULT 0,
    checks_total INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    source_reusable INTEGER DEFAULT 0,
    expiry_date TEXT,
    ocr_source TEXT DEFAULT '',
    uploaded_at TEXT NOT NULL,
    uploaded_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clarification_requests (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    raised_by TEXT NOT NULL,
    ai_drafted_text TEXT DEFAULT '',
    final_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    applicant_response TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    responded_at TEXT
);

CREATE TABLE IF NOT EXISTS inspections (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    type TEXT NOT NULL,
    scheduled_date TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    coordinated_with TEXT DEFAULT '[]',
    is_post_facto_audit INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schemes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    eligibility TEXT DEFAULT '[]',
    benefits TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS grievances (
    id TEXT PRIMARY KEY,
    application_id TEXT,
    user_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    description TEXT DEFAULT '',
    escalation_level INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT DEFAULT '',
    action TEXT NOT NULL,
    reasoning TEXT DEFAULT '',
    decision_source TEXT DEFAULT 'human',
    meta TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE not permitted');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: DELETE not permitted');
END;

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    application_id TEXT,
    channel TEXT DEFAULT 'in_app',
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    status TEXT DEFAULT 'queued',
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS kyc_consents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    aadhaar_last4 TEXT DEFAULT '',
    digilocker_ref TEXT DEFAULT '',
    otp_hash TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending_otp',
    verified_data TEXT DEFAULT '{}',
    kyc_source TEXT DEFAULT 'digilocker-sandbox',
    attempts INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    verified_at TEXT
);

CREATE TABLE IF NOT EXISTS generated_forms (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    business_id TEXT NOT NULL,
    filename TEXT DEFAULT '',
    file_ref TEXT DEFAULT '',
    sha256 TEXT DEFAULT '',
    verification_code TEXT DEFAULT '',
    source TEXT DEFAULT 'kyc-autofill',
    checklist_snapshot TEXT DEFAULT '{}',
    generated_at TEXT NOT NULL,
    submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS parameter_signoffs (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    officer_id TEXT NOT NULL,
    param_key TEXT NOT NULL,
    param_label TEXT DEFAULT '',
    deterministic_state TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(application_id, param_key)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apps_business ON applications(business_id);
CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_docs_app ON documents(application_id);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id);
"""


def _seed_settings() -> None:
    if query_one("SELECT value FROM settings WHERE key='green_channel_enabled'") is None:
        execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('green_channel_enabled', ?)",
            (jdumps({"enabled": config.GREEN_CHANNEL_ENABLED}),),
        )


def _seed_demo_users() -> None:
    from .security import hash_password

    if query_one("SELECT id FROM users LIMIT 1") is not None:
        return
    users = [
        ("usr_applicant_demo", "Demo Entrepreneur", "9000000001", "applicant@demo.in",
         "Demo@123", "applicant"),
        ("usr_officer_demo", "Demo Officer", "9000000002", "officer@demo.in",
         "Demo@123", "officer"),
        ("usr_admin_demo", "Demo Admin", "9000000003", "admin@demo.in",
         "Demo@123", "admin"),
    ]
    for uid, name, phone, email, pw, role in users:
        execute(
            "INSERT OR IGNORE INTO users (id, name, phone, email, password_hash, role, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, name, phone, email, hash_password(pw), role, _now()),
        )


def _seed_approvals() -> None:
    from .core.rule_engine import load_all_rules

    rules = load_all_rules()
    now = _now()
    rows = []
    for sector, data in rules["sectors"].items():
        for appr in data["approvals"]:
            rows.append((
                appr["id"], sector, appr["code"], appr["name"], appr["department"],
                appr.get("description", ""), int(appr.get("sla_days", 15)),
                jdumps(appr.get("required_documents", [])),
                jdumps(appr.get("dependency_ids", [])),
                appr.get("parallel_group", ""),
                jdumps(appr.get("condition")) if appr.get("condition") else "",
                1 if appr.get("green_channel_eligible") else 0,
                now,
            ))
    executemany(
        "INSERT OR IGNORE INTO approvals (id, sector, code, name, department, description, "
        "sla_days, required_documents, dependency_ids, parallel_group, condition_rule, "
        "green_channel_eligible, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def _seed_schemes() -> None:
    schemes = [
        ("sch_msme", "MSME Udyam Subsidy (Maharashtra)",
         "Capital investment subsidy for registered MSME manufacturing units.",
         [{"field": "sector", "op": "in",
           "value": ["food_processing", "textiles", "chemicals", "pharma",
                      "automotive"]},
          {"field": "investment_size", "op": "lte", "value": 50000000}],
         "5-10% capital subsidy, electricity duty exemption"),
        ("sch_food_park", "Food Processing Mega Food Park Incentive",
         "Support for food processing units in designated parks.",
         [{"field": "sector", "op": "eq", "value": "food_processing"},
          {"field": "investment_size", "op": "gte", "value": 1000000}],
         "Grant support, common facility access"),
        ("sch_textile_policy", "Maharashtra Textile Policy 2023 Incentives",
         "Incentives for textile units including power tariff subsidy.",
         [{"field": "sector", "op": "eq", "value": "textiles"}],
         "Power tariff subsidy, interest subvention"),
        ("sch_chem_safety", "Chemical Sector Safety & Compliance Support",
         "Support for safety systems and compliance tooling in chemical units.",
         [{"field": "sector", "op": "eq", "value": "chemicals"},
          {"field": "investment_size", "op": "lte", "value": 100000000}],
         "Safety audit subsidy, hazardous-waste handling support"),
        ("sch_pharma_park", "Pharma Park & Life Sciences Incentive",
         "Incentives for pharmaceutical units in designated pharma parks.",
         [{"field": "sector", "op": "eq", "value": "pharma"}],
         "Stamp duty exemption, R&D grant support"),
        ("sch_auto_cluster", "Auto Cluster Development Incentive",
         "Support for auto component units joining MSME auto clusters.",
         [{"field": "sector", "op": "eq", "value": "automotive"}],
         "Cluster facility access, capital equipment subsidy"),
        ("sch_mega", "Mega Project Incentive",
         "For large investments above Rs. 100 crore.",
         [{"field": "investment_size", "op": "gte", "value": 1000000000}],
         "Stamp duty exemption, SGST reimbursement"),
    ]
    # Upsert (not INSERT OR IGNORE) so refreshed seeds reach existing demo DBs.
    executemany(
        "INSERT INTO schemes (id, name, description, eligibility, benefits) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
        "description=excluded.description, eligibility=excluded.eligibility, "
        "benefits=excluded.benefits",
        [(sid, n, d, jdumps(e), b) for sid, n, d, e, b in schemes],
    )


def init_db() -> None:
    conn = get_conn()
    with _write_lock:
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_PART2)
        conn.commit()
    _seed_settings()
    _seed_demo_users()
    try:
        _seed_approvals()
    except Exception:
        pass  # rule-engine problems must never block startup
    _seed_schemes()


def get_setting(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return jloads(row["value"], default) if row else default


def set_setting(key: str, value: Any) -> None:
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, jdumps(value)))


