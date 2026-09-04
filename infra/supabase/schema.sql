-- SIH26130 — Supabase Postgres schema (production target).
-- The local demo uses SQLite (backend/app/db.py) mirroring this schema.
-- Enable pgcrypto for column-level encryption if not using app-level AES.

create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    phone text unique,
    email text unique,
    password_hash text not null,
    role text not null check (role in ('applicant','officer','admin','consultant')),
    created_at timestamptz not null default now()
);

create table if not exists business_profiles (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null unique references users(id),
    name text not null,
    sector text not null,
    district text default '',
    industrial_zone text default '',
    investment_size numeric default 0,
    employee_count integer default 0,
    project_stage text default 'planning',
    authorized_person text default '',
    pan_enc text default '',        -- Fernet/pgcrypto-encrypted
    pan_masked text default '',     -- XXXXX1234F style
    pan_hash text default '',       -- sha256 reference (never raw PAN)
    gst_enc text default '',
    gst_masked text default '',
    gst_hash text default '',
    registration_no text default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists approvals (
    id text primary key,
    sector text not null,
    code text not null,
    name text not null,
    department text not null,
    description text default '',
    sla_days integer not null,
    required_documents jsonb not null,
    dependency_ids jsonb default '[]',
    parallel_group text default '',
    condition_rule jsonb,
    green_channel_eligible boolean default false,
    created_at timestamptz not null default now()
);

create table if not exists applications (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references business_profiles(id),
    approval_id text not null references approvals(id),
    status text not null default 'draft',
    submitted_at timestamptz,
    sla_deadline timestamptz,
    assigned_officer_id uuid,
    decision_source text check (decision_source in ('human','system')),
    decision_notes text default '',
    decided_at timestamptz,
    readiness_score numeric default 0,
    readiness_breakdown jsonb default '[]',
    green_channel boolean default false,
    provisional_certificate jsonb,
    created_at timestamptz not null default now()
);

create table if not exists documents (
    id uuid primary key default gen_random_uuid(),
    application_id uuid not null references applications(id),
    business_id uuid not null,
    type text not null,
    label text default '',
    filename text default '',
    file_ref text default '',       -- Supabase Storage object path (private bucket)
    mime text default '',
    size integer default 0,
    extracted_fields jsonb default '{}',
    validation_flags jsonb default '[]',
    checks_passed integer default 0,
    checks_total integer default 0,
    status text not null default 'pending',
    source_reusable boolean default false,
    expiry_date date,
    ocr_source text default '',
    uploaded_at timestamptz not null default now(),
    uploaded_by uuid not null
);

create table if not exists clarification_requests (
    id uuid primary key default gen_random_uuid(),
    application_id uuid not null references applications(id),
    raised_by uuid not null,
    ai_drafted_text text default '',   -- AI suggestion (separate from fact)
    final_text text not null,          -- officer-edited authoritative text
    status text not null default 'open',
    applicant_response text default '',
    created_at timestamptz not null default now(),
    responded_at timestamptz
);

create table if not exists inspections (
    id uuid primary key default gen_random_uuid(),
    application_id uuid not null references applications(id),
    type text not null,
    scheduled_date date,
    status text not null default 'scheduled',
    coordinated_with jsonb default '[]',
    is_post_facto_audit boolean default false,
    created_at timestamptz not null default now()
);

create table if not exists schemes (
    id text primary key,
    name text not null,
    description text default '',
    eligibility jsonb default '[]',
    benefits text default ''
);

create table if not exists grievances (
    id uuid primary key default gen_random_uuid(),
    application_id uuid,
    user_id uuid not null,
    reason text not null,
    description text default '',
    escalation_level integer default 0,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    resolved_at timestamptz
);

create table if not exists audit_log (
    id uuid primary key default gen_random_uuid(),
    entity_type text not null,
    entity_id text not null,
    actor_id text not null,          -- user id or 'system'
    actor_role text default '',
    action text not null,
    reasoning text default '',
    decision_source text default 'human' check (decision_source in ('human','system')),
    meta jsonb default '{}',
    created_at timestamptz not null default now()
);

-- FR-29 / 3.7: audit trail is append-only at the DB level.
create or replace function forbid_audit_mutation() returns trigger as $$
begin
    raise exception 'audit_log is append-only: % not permitted', tg_op;
end;
$$ language plpgsql;

create trigger audit_log_no_update
before update on audit_log
for each row execute function forbid_audit_mutation();

create trigger audit_log_no_delete
before delete on audit_log
for each row execute function forbid_audit_mutation();

create table if not exists notifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    application_id uuid,
    channel text default 'in_app',
    title text not null,
    body text default '',
    status text default 'queued',
    created_at timestamptz not null default now(),
    sent_at timestamptz
);

create table if not exists settings (
    key text primary key,
    value jsonb not null
);

create index if not exists idx_apps_business on applications(business_id);
create index if not exists idx_apps_status on applications(status);
create index if not exists idx_docs_app on documents(application_id);
create index if not exists idx_notif_user on notifications(user_id);


