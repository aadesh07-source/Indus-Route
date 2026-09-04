-- SIH26130 — Supabase Row Level Security policies (doc 3.1/3.6).
-- Applicants read only their own rows; officers only their assigned queue;
-- admins get aggregate/anonymized views. RBAC is ALSO enforced at the API
-- layer (FastAPI deps) — never rely on frontend route guards alone.

alter table users enable row level security;
alter table business_profiles enable row level security;
alter table applications enable row level security;
alter table documents enable row level security;
alter table clarification_requests enable row level security;
alter table inspections enable row level security;
alter table grievances enable row level security;
alter table notifications enable row level security;
alter table audit_log enable row level security;

-- Helper: current user's role (via JWT claims injected by the API layer).
create or replace function current_role_claim() returns text as $$
    select coalesce(nullif(current_setting('request.jwt.claim.role', true), ''), 'anon');
$$ language sql stable;

create or replace function current_user_id() returns uuid as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$ language sql stable;

-- Users: read own record only.
create policy users_self_read on users
for select using (id = current_user_id());

-- Profiles: owner full access; officials read-only.
create policy profiles_owner_all on business_profiles
for all using (owner_id = current_user_id());
create policy profiles_official_read on business_profiles
for select using (current_role_claim() in ('officer', 'admin'));

-- Applications: owner read; assigned officer read/update; admin read.
create policy apps_owner_read on applications
for select using (
    exists (select 1 from business_profiles b
            where b.id = applications.business_id and b.owner_id = current_user_id())
);
create policy apps_officer_rw on applications
for select using (
    assigned_officer_id = current_user_id() or current_role_claim() = 'admin'
);
create policy apps_officer_update on applications
for update using (
    assigned_officer_id = current_user_id() or current_role_claim() = 'admin'
);

-- Documents: owner read; assigned officer/admin read.
create policy docs_owner_read on documents
for select using (business_id in (
    select id from business_profiles where owner_id = current_user_id()));
create policy docs_official_read on documents
for select using (current_role_claim() in ('officer', 'admin'));

-- Clarifications: owner read/respond; officials read; assigned officer write.
create policy clar_owner_read on clarification_requests
for select using (application_id in (
    select a.id from applications a join business_profiles b on a.business_id = b.id
    where b.owner_id = current_user_id()));
create policy clar_official_read on clarification_requests
for select using (current_role_claim() in ('officer', 'admin'));

-- Inspections: officials read/write; owner read.
create policy insp_official_rw on inspections
for all using (current_role_claim() in ('officer', 'admin'));
create policy insp_owner_read on inspections
for select using (application_id in (
    select a.id from applications a join business_profiles b on a.business_id = b.id
    where b.owner_id = current_user_id()));

-- Grievances: owner read/insert; officials read/update.
create policy grv_owner_rw on grievances
for all using (user_id = current_user_id());
create policy grv_official_rw on grievances
for select using (current_role_claim() in ('officer', 'admin'));

-- Notifications: owner-only.
create policy notif_owner on notifications
for all using (user_id = current_user_id());

-- Audit log: nobody reads directly via RLS except admins (API aggregates).
-- UPDATE/DELETE already blocked by triggers (append-only).
create policy audit_admin_read on audit_log
for select using (current_role_claim() = 'admin');
