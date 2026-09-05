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
        status TEXT NOT NULL CHECK (status IN ('draft','submitted','under_review','clarification_pending','approved','rejected','provisionally_cleared','returned')) DEFAULT 'draft',
    submitted_at TEXT,
    sla_deadline TEXT,
    assigned_officer_id TEXT,
    decision_source TEXT,
    decision_notes TEXT DEFAULT '',
    decided_at TEXT,
    feedback TEXT DEFAULT '',
    readiness_score REAL DEFAULT 0,
    readiness_breakdown TEXT DEFAULT '[]',
    green_channel INTEGER DEFAULT 0,
    provisional_certificate TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    selected_schemes TEXT DEFAULT '[]'
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

CREATE TABLE IF NOT EXISTS certificates (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    business_id TEXT NOT NULL,
    certificate_no TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'sanction_clearance',
    issued_at TEXT NOT NULL,
    issuing_officer_id TEXT,
    subject_to TEXT DEFAULT '{}',
    verification_hash TEXT DEFAULT '',
    pdf_ref TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    form_data TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS send_back_logs (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    officer_id TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
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

CREATE TABLE IF NOT EXISTS application_schemes (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id),
    scheme_id TEXT NOT NULL REFERENCES schemes(id),
    selected_at TEXT NOT NULL,
    UNIQUE(application_id, scheme_id)
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


DEMO_INDUSTRIES = [
    {
        "id": "usr_app_foods", "demo_id": "PUNE-FOODS-001",
        "name": "Pune Foods Pvt Ltd", "phone": "9000000001",
        "email": "punefoods@demo.in", "password": "Foods@2026", "sector": "food_processing",
        "industry_label": "Food Processing",
        "company": "Pune Foods Pvt Ltd",
        "district": "Pune", "zone": "MIDC Chakan",
        "investment": 25_000_000, "employees": 45,
        "pan": "AAACP1234F", "gst": "27AAACP1234F1Z5",
    },
    {
        "id": "usr_app_pharma", "demo_id": "PUNE-PHARMA-002",
        "name": "Pune Pharma Labs", "phone": "9000000011",
        "email": "punepharma@demo.in", "password": "Pharma@2026", "sector": "pharma",
        "industry_label": "Pharmaceuticals & Bulk Drug",
        "company": "Pune Pharma Labs Ltd",
        "district": "Pune", "zone": "MIDC Pimpri",
        "investment": 75_000_000, "employees": 120,
        "pan": "AABCP2345G", "gst": "27AABCP2345G1Z6",
    },
    {
        "id": "usr_app_auto", "demo_id": "PUNE-AUTO-003",
        "name": "Pune Auto Components", "phone": "9000000021",
        "email": "puneauto@demo.in", "password": "Auto@2026", "sector": "automotive",
        "industry_label": "Automobile & Heavy Engineering",
        "company": "Pune Auto Components Pvt Ltd",
        "district": "Pune", "zone": "MIDC Bhosari",
        "investment": 120_000_000, "employees": 230,
        "pan": "AADCP3456H", "gst": "27AADCP3456H1Z7",
    },
    {
        "id": "usr_app_esdm", "demo_id": "PUNE-ESDM-004",
        "name": "Pune ESDM Systems", "phone": "9000000031",
        "email": "puneesdm@demo.in", "password": "Esdm@2026", "sector": "electronics",
        "industry_label": "Electronics & Semiconductor (ESDM)",
        "company": "Pune ESDM Systems Pvt Ltd",
        "district": "Pune", "zone": "MIDC Hinjawadi",
        "investment": 95_000_000, "employees": 80,
        "pan": "AAECP4567I", "gst": "27AAECP4567I1Z8",
    },
    {
        "id": "usr_app_logi", "demo_id": "PUNE-LOGI-005",
        "name": "Pune Logistics Hub", "phone": "9000000041",
        "email": "punelogistics@demo.in", "password": "Logi@2026", "sector": "logistics",
        "industry_label": "Logistics & Cold Chain",
        "company": "Pune Logistics Hub Pvt Ltd",
        "district": "Pune", "zone": "MIDC Talegaon",
        "investment": 55_000_000, "employees": 60,
        "pan": "AAFCP5678J", "gst": "27AAFCP5678J1Z9",
    },
    {
        "id": "usr_app_dist", "demo_id": "PUNE-DIST-006",
        "name": "Pune Distillery Co.", "phone": "9000000051",
        "email": "punedistillery@demo.in", "password": "Distill@2026", "sector": "distillery",
        "industry_label": "Distilleries & Breweries",
        "company": "Pune Distillery Co Pvt Ltd",
        "district": "Pune", "zone": "MIDC Baramati",
        "investment": 180_000_000, "employees": 150,
        "pan": "AAGCP6789K", "gst": "27AAGCP6789K1Z1",
    },
    {
        "id": "usr_app_energy", "demo_id": "PUNE-ENERGY-007",
        "name": "Pune Renewable Energy", "phone": "9000000061",
        "email": "punerenew@demo.in", "password": "Energy@2026", "sector": "energy",
        "industry_label": "Renewable Energy & Data Centers",
        "company": "Pune Renewable Energy Pvt Ltd",
        "district": "Pune", "zone": "MIDC Ranjangaon",
        "investment": 250_000_000, "employees": 90,
        "pan": "AAHCP7890L", "gst": "27AAHCP7890L1Z2",
    },
]


def _seed_demo_users() -> None:
    from .security import hash_password

    base_users = [
        ("usr_officer_demo", "Demo Officer", "9000000002", "officer@demo.in",
         "Demo@123", "officer"),
        ("usr_admin_demo", "Demo Admin", "9000000003", "admin@demo.in",
         "Demo@123", "admin"),
    ]
    for uid, name, phone, email, pw, role in base_users:
        execute(
            "INSERT OR IGNORE INTO users (id, name, phone, email, password_hash, role, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, name, phone, email, hash_password(pw), role, _now()),
        )
    for ind in DEMO_INDUSTRIES:
        execute(
            "INSERT INTO users (id, name, phone, email, password_hash, role, created_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, phone=excluded.phone, "
            "email=excluded.email, password_hash=excluded.password_hash, role=excluded.role",
            (ind["id"], ind["name"], ind["phone"], ind["email"],
             hash_password(ind.get("password", "Demo@123")), "applicant", _now()),
        )

def _seed_demo_business_profiles() -> None:
    """Create a pre-filled business profile per industry demo so that the
    rule engine produces a personalised checklist immediately on login."""
    from .core import pii

    now = _now()
    for ind in DEMO_INDUSTRIES:
        profile_id = "biz_" + ind["id"].replace("usr_app_", "")
        existing = query_one("SELECT id FROM business_profiles WHERE id=?",
                             (profile_id,))
        if existing:
            continue
        execute(
            "INSERT INTO business_profiles "
            "(id, owner_id, name, sector, district, industrial_zone, investment_size, "
            "employee_count, project_stage, authorized_person, "
            "pan_enc, pan_masked, pan_hash, gst_enc, gst_masked, gst_hash, "
            "registration_no, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile_id, ind["id"], ind["company"], ind["sector"], ind["district"],
             ind["zone"], ind["investment"], ind["employees"], "planning", ind["name"],
             pii.encrypt_value(ind["pan"]), pii.mask_value(ind["pan"]),
             pii.reference_hash(ind["pan"]),
             pii.encrypt_value(ind["gst"]), pii.mask_value(ind["gst"]),
             pii.reference_hash(ind["gst"]), ind["demo_id"], now, now),
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
        # ── Universal baseline: PSI / MIISP (all manufacturing sectors) ──
        ("psi_ips", "PSI · Investment Promotion Subsidy (IPS)",
         "Package Scheme of Incentives: refund of net SGST paid on sales, scaled "
         "by taluka category (Group A to D+/Vidarbha/Marathwada) and capped by "
         "eligible Fixed Capital Investment (FCI).",
         [{"field": "sector", "op": "in",
           "value": ["food_processing", "textiles", "chemicals", "pharma",
                      "automotive", "electronics", "logistics", "energy",
                      "distillery"]}],
         "40% to 100% refund of net SGST paid • 7 to 10 year eligibility window "
         "• cap linked to eligible Fixed Capital Investment"),
        ("psi_stamp", "PSI · Stamp Duty Exemption",
         "Waiver of stamp duty on land purchase, lease deeds and bank mortgage "
         "documents, highest in backward taluka zones (C, D and D+ categories).",
         [{"field": "sector", "op": "in",
           "value": ["food_processing", "textiles", "chemicals", "pharma",
                      "automotive", "electronics", "logistics", "energy",
                      "distillery"]}],
         "Up to 100% stamp duty waiver in C/D/D+ zones • covers land purchase, "
         "lease deeds and mortgage documents"),
        ("psi_interest", "PSI · Interest Subsidy (MSME Term Loans)",
         "Annual interest subvention on term loans taken for eligible plant & "
         "machinery by MSME manufacturing units.",
         [{"field": "sector", "op": "in",
           "value": ["food_processing", "textiles", "chemicals", "pharma",
                      "automotive", "electronics", "logistics", "energy",
                      "distillery"]},
          {"field": "investment_size", "op": "lte", "value": 50000000}],
         "5% annual interest subvention on term loans • applies to eligible "
         "plant & machinery financing"),
        ("psi_power", "PSI · Power Tariff & Electricity Duty Relief",
         "Electricity duty exemption plus a state power tariff subsidy for "
         "eligible manufacturing units.",
         [{"field": "sector", "op": "in",
           "value": ["food_processing", "textiles", "chemicals", "pharma",
                      "automotive", "electronics", "logistics", "energy",
                      "distillery"]}],
         "Electricity duty exemption for 7-10 years • power tariff reduction of "
         "Rs 0.50 to Rs 1.00 per unit"),
        ("sch_msme", "MSME Udyam Subsidy (Maharashtra)",
         "Capital investment subsidy for registered MSME manufacturing units.",
         [{"field": "sector", "op": "in",
           "value": ["food_processing", "textiles", "chemicals", "pharma",
                      "automotive"]},
          {"field": "investment_size", "op": "lte", "value": 50000000}],
         "5-10% capital subsidy, electricity duty exemption"),
        ("sch_food_park", "PM Kisan SAMPADA Yojana — Mega Food Parks & Cold Chain",
         "Central MoFPI capital grant for integrated cold chains, preservation "
         "and value-addition infrastructure for food processing units.",
         [{"field": "sector", "op": "eq", "value": "food_processing"},
          {"field": "investment_size", "op": "gte", "value": 1000000}],
         "35% to 50% capital grant • integrated cold chain, preservation and "
         "value-addition infrastructure support"),
        ("cefppc", "CEFPPC — Food Processing & Preservation Capacity",
         "Central MoFPI capital subsidy on core processing machinery under the "
         "Creation/Expansion of Food Processing & Preservation Capacities scheme.",
         [{"field": "sector", "op": "eq", "value": "food_processing"}],
         "Up to Rs 5 Crore capital subsidy on core processing machinery"),
        ("pmfme", "PMFME — Micro Food Processing Enterprises (ODOP)",
         "Credit-linked capital subsidy under the One District One Product "
         "(ODOP) cluster approach for micro food processing enterprises.",
         [{"field": "sector", "op": "eq", "value": "food_processing"},
          {"field": "investment_size", "op": "lte", "value": 10000000}],
         "35% credit-linked capital subsidy • up to Rs 10 Lakh per unit • ODOP "
         "cluster approach"),
        ("mh_food_addon", "Maharashtra Priority Sector Add-on (Food)",
         "State policy add-on for secondary/tertiary food processing units, "
         "stackable on central food-processing incentives.",
         [{"field": "sector", "op": "eq", "value": "food_processing"}],
         "Additional 20% subsidy on Fixed Capital Investment • 2 extra years of "
         "SGST refund under state policy"),
        ("sch_textile_policy", "Maharashtra State Textile Policy 2023",
         "State textile policy incentives: capital subsidy on new machinery "
         "(extra for cotton-growing Vidarbha/Marathwada) plus dedicated power "
         "tariff rebate for spinning, weaving and processing units.",
         [{"field": "sector", "op": "eq", "value": "textiles"}],
         "10% to 25% capital subsidy on new machinery • +10% in cotton-growing "
         "regions • concessional power tariff (approx. Rs 2-3/unit rebate)"),
        ("atufs", "ATUFS / PM-MITRA — Technology Upgradation",
         "Central capital investment subsidy for technology modernization, "
         "garmenting and technical textile manufacturing.",
         [{"field": "sector", "op": "eq", "value": "textiles"}],
         "10% to 15% central capital investment subsidy • technology "
         "modernization, garmenting and technical textiles"),
        ("sch_chem_safety", "Chemical Sector Safety & Compliance Support",
         "Support for safety systems and compliance tooling in chemical units.",
         [{"field": "sector", "op": "eq", "value": "chemicals"},
          {"field": "investment_size", "op": "lte", "value": 100000000}],
         "Safety audit subsidy, hazardous-waste handling support"),
        ("sch_pharma_park", "Bulk Drug Park / Pharma Cluster Assistance",
         "State capital grants for shared pharma infrastructure: Common "
         "Effluent Treatment Plants, solvent recovery and centralized steam "
         "generation in designated pharma clusters.",
         [{"field": "sector", "op": "eq", "value": "pharma"}],
         "State capital grants up to 70% for CETP • solvent recovery plants • "
         "centralized steam generation"),
        ("pli_bulk_drugs", "PLI — Bulk Drugs & Medical Devices",
         "Production Linked Incentive on incremental domestic sales of critical "
         "Key Starting Materials (KSMs), drug intermediates and APIs.",
         [{"field": "sector", "op": "eq", "value": "pharma"}],
         "5% to 20% financial incentive on incremental domestic sales • KSMs, "
         "drug intermediates and APIs"),
        ("pharma_rd", "R&D & Quality Certification Assistance (State MSME)",
         "Reimbursement of certification and compliance costs for pharma and "
         "life-science units under the state MSME scheme.",
         [{"field": "sector", "op": "eq", "value": "pharma"}],
         "50% reimbursement up to Rs 10 Lakh • WHO-GMP, USFDA and ISO "
         "compliance certifications"),
        ("sch_auto_cluster", "MSE-CDP — Cluster Development Programme",
         "Grant-in-aid for Common Facility Centres serving auto component "
         "clusters: tooling, die-casting and heat-treatment facilities.",
         [{"field": "sector", "op": "eq", "value": "automotive"}],
         "Up to 70% grant-in-aid for Common Facility Centres (CFC) • tooling, "
         "die-casting and heat-treatment facilities"),
        ("mh_ev_policy", "Maharashtra EV Policy Incentives",
         "Pioneer/Mega status benefits for EV manufacturing and battery "
         "assembly plants; transition support for MSME component suppliers "
         "moving to EV drivetrains.",
         [{"field": "sector", "op": "eq", "value": "automotive"}],
         "100% stamp duty waiver for EV/battery plants • SGST refund and custom "
         "fiscal packages • up to 15% capital subsidy for MSME EV transition"),
        ("capital_goods", "Capital Goods Scheme (Ministry of Heavy Industries)",
         "Central funding for technology acquisition, robotic cells and "
         "high-precision testing centres for engineering units.",
         [{"field": "sector", "op": "eq", "value": "automotive"}],
         "Up to 25% funding for technology acquisition • robotic cells and "
         "high-precision testing centres"),
        ("msips_specs", "M-SIPS / SPECS — Electronics Manufacturing",
         "Financial incentive on capital expenditure for electronic components, "
         "semiconductor packaging and PCB assembly.",
         [{"field": "sector", "op": "eq", "value": "electronics"}],
         "25% financial incentive on capital expenditure • electronic "
         "components, semiconductor packaging and PCB assembly"),
        ("dli_scheme", "Design Linked Incentive (DLI) Scheme",
         "Financial support for indigenous semiconductor design and IP "
         "development by ESDM companies.",
         [{"field": "sector", "op": "eq", "value": "electronics"}],
         "Up to 50% of eligible expenditure • indigenous semiconductor design "
         "and IP development"),
        ("mh_electronics", "Maharashtra Electronics Policy (EMC Benefits)",
         "State electronics policy benefits for units in designated Electronics "
         "Manufacturing Clusters: power duty relief and land allotment rebates.",
         [{"field": "sector", "op": "eq", "value": "electronics"}],
         "100% electricity duty exemption for 10 years • special land allotment "
         "rebates in designated EMCs"),
        ("mh_logistics_policy", "Maharashtra Logistics Policy",
         "State logistics policy benefits for integrated multi-modal logistic "
         "parks and automated high-rack warehouses along freight corridors.",
         [{"field": "sector", "op": "eq", "value": "logistics"}],
         "Concessional industrial power tariffs (treated on par with industrial "
         "units) • FSI incentives up to 2.0+ for automated high-rack warehouses "
         "on Samruddhi Mahamarg / JNPA port belt"),
        ("midh_coldchain", "MIDH — Horticulture Cold Storage & Reefer Subsidy",
         "Credit-linked capital subsidy for cold storage construction and "
         "reefer transport under the horticulture development mission.",
         [{"field": "sector", "op": "eq", "value": "logistics"}],
         "Up to 35% credit-linked capital subsidy • cold storage construction "
         "and reefer transport vans"),
        ("satat_cbg", "SATAT — Compressed Biogas (Bio-CNG) Plants",
         "Central financial assistance for Compressed Biogas production plants "
         "under the Sustainable Alternative Towards Affordable Transportation "
         "initiative.",
         [{"field": "sector", "op": "eq", "value": "energy"}],
         "Central financial assistance up to Rs 4 Crore per CBG / Bio-CNG plant"),
        ("mh_green_energy", "Maharashtra Green Energy Policy",
         "Duty and surcharge exemptions for captive renewable projects plus "
         "priority clearances for green manufacturing facilities.",
         [{"field": "sector", "op": "eq", "value": "energy"}],
         "100% exemption on electricity duty and open-access cross-subsidy "
         "surcharges for captive solar/wind • priority Green Channel clearances "
         "for biofuel, solar cell and green hydrogen facilities"),
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
    _seed_demo_business_profiles()
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


