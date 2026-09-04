# SIH26130 — Intelligent Industrial Approval & Compliance Management Platform

End-to-end implementation of the SIH26130 problem statement: streamlining
industrial approvals and compliance for Maharashtra, with a deterministic
rule engine at the core and an advisory-only AI layer.

**Guiding principle (enforced in code):** *Rules decide. AI explains,
extracts, flags, drafts, summarizes.* Readiness is a rubric-based
completeness score — never a risk score or approval probability.

## Quick start

### Backend (FastAPI, zero external services required)

```powershell
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Runs immediately with a local SQLite store (`backend/data/sih.db`),
  auto-seeded with demo users, sector rule tables and schemes.
- Interactive API docs: <http://127.0.0.1:8000/docs>
- Health/system status: <http://127.0.0.1:8000/health>

Demo accounts (seeded automatically):

| Role | Phone | Password |
|---|---|---|
| Applicant | 9000000001 | Demo@123 |
| Officer | 9000000002 | Demo@123 |
| Admin | 9000000003 | Demo@123 |

Officer/admin self-registration requires the invite code
`MAHARASHTRA-2026` (configurable via `SIH_ADMIN_INVITE_CODE`).

### Frontend (Next.js)

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. API calls are proxied to the backend via a
Next.js rewrite (`/api/* -> http://127.0.0.1:8000/*`).

### End-to-end verification

```powershell
# with the backend running:
python backend/tests/smoke_test.py http://127.0.0.1:8000
```

36 checks covering auth/RBAC, profiles, deterministic checklist, document
pre-validation, Green Channel issuance, officer workflow, admin analytics
and the audit trail.

## Architecture

```
frontend/  Next.js (applicant / officer / admin portals, lib/api.ts client)
backend/
  app/main.py            FastAPI app: CORS, rate limiting, error handling
  app/config.py          env-driven settings with safe defaults (never crashes)
  app/db.py              SQLite store mirroring the Supabase schema + seeds
  app/security.py        stdlib JWT (HS256) + PBKDF2 hashing (no deps)
  app/core/rule_engine.py   PURE deterministic engine (JSON rule tables)
  app/core/ocr_service.py   file magic-byte validation, OCR, check validators
  app/core/readiness.py     rubric-based explainable readiness score
  app/core/green_channel.py Green Channel extension (constrained, audited)
  app/core/ai_service.py    Gemini (optional) — summarize/draft/RAG only
  app/core/digilocker.py    DigiLocker/Aadhaar e-KYC adapter (sandbox mode;
                            full Aadhaar never stored — last-4 ref only)
  app/core/form_pdf.py      stdlib-only Unified Application Form PDF writer
  app/core/scheduler.py     SLA monitor (APScheduler, thread fallback)
  app/core/pii.py           PAN/GST encrypt+hash+mask (Aadhaar never stored)
  app/notifications/sms_gateway.py  Termux webhook client (optional)
  app/rules/*.json       food_processing, textiles, chemicals, pharma,
                         automotive, document_checks
  tests/smoke_test.py    end-to-end verification (36 checks)
  tests/autofill_test.py auto-form pipeline verification (27 checks)
infra/supabase/           production schema.sql + rls-policies.sql
```

## Auto-Form Pipeline (DigiLocker → PDF → instant officer routing → 1-click approve)

The applicant-to-approval flow can run end-to-end with zero manual form entry:

1. **DigiLocker e-KYC** — applicant enters their Aadhaar number, receives an
   OTP (sandbox shows it in-app; production sends it via the SMS gateway),
   and the verified identity is merged into the business profile. The full
   Aadhaar number is used transiently and **never stored** (last-4 + consent
   reference only). With `SIH_DIGILOCKER_CLIENT_ID`/`_SECRET` configured the
   same interface calls the real API Setu endpoints.
2. **Auto-generated Unified Application Form (PDF)** — a stdlib-only PDF
   writer compiles the e-KYC data, business profile, the deterministic
   sector-clearance checklist and the document pre-validation matrix into an
   official-looking form with a SHA-256 integrity hash, a verification code
   (check: `GET /forms/verify/{code}`) and a hash-pattern verification block.
3. **Instant dispatch** — `POST /applications/{id}/submit-form` moves the
   application into the officer queue and notifies every officer immediately;
   the officer portal polls a lightweight queue-version endpoint (4s) and
   refreshes the moment an application lands (Supabase Realtime/WebSockets
   replace this in production).
4. **AI pre-scrutiny + all-green matrix** — the officer review console shows
   the auto-form provenance (verification code, e-KYC binding), the
   deterministic per-document checklist, and a computed `all_green` state.
5. **1-Click Instant Approve** — when every statutory parameter is green the
   officer can approve in one click. The system never auto-approves a final
   decision: the button is merely enabled by deterministic checks; the human
   officer still decides (and can always clarify or reject instead).

Try it end-to-end: `python backend/tests/autofill_test.py http://127.0.0.1:8000`

## Key design decisions

1. **Deterministic rule engine, zero I/O** — approvals/SLAs/parallel groups
   come from `app/rules/*.json`; the engine is a pure function, unit-testable
   and provably deterministic to judges (`POST /rule-engine/evaluate`).
2. **AI strictly downstream** — Gemini is optional. Every AI call has a
   timeout and a deterministic fallback; OCR/user text is quarantined as
   `<user_data>` in prompts (injection containment); RAG answers cite rule
   sources or respond "not found in the rule set".
3. **Green Channel (extension)** — fires only on 100% deterministic pass of
   whitelisted approvals + two-source PAN↔GSTIN cross-check, rate-limited per
   business/day, globally toggleable by admins, and always issues a
   *provisional* certificate with a mandatory post-facto audit inspection
   created in the same transaction. Audit-logged with
   `decision_source=system`. QR payload contains a verification hash, no PII.
4. **Robustness** — no missing env var, missing optional dependency
   (EasyOCR, APScheduler, cryptography), or unreachable external service can
   crash the API; every path degrades gracefully and reports its mode via
   `/health`.
5. **Security** — JWT bearer auth, role checks at the API layer, SQLite
   triggers making `audit_log` append-only (mirrored by Postgres triggers +
   RLS policies in `infra/supabase/`), magic-byte file validation, private
   file store, PAN/GST encrypted+hashed+masked, Aadhaar never stored.

## Configuration

Copy `backend/.env.example` to `backend/.env` (or export the vars). All
settings are optional — sensible defaults keep everything running.

| Variable | Purpose |
|---|---|
| `SIH_SECRET_KEY` | JWT + PII encryption key |
| `SIH_ADMIN_INVITE_CODE` | invite code for officer/admin signup |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | enable the Gemini advisory layer |
| `SIH_SMS_WEBHOOK_URL` / `SIH_SMS_WEBHOOK_TOKEN` | Termux SMS gateway |
| `SIH_GREEN_CHANNEL_ENABLED` | default Green Channel state |
| `SIH_MAX_UPLOAD_MB` | upload size limit |

## Production path (Supabase)

Run `infra/supabase/schema.sql` and `rls-policies.sql` on a Supabase
project, move document blobs to a private Storage bucket, and point the
backend's data layer at Postgres — the schema is identical to the SQLite
demo store. Replace the Termux SMS relay with a licensed DLT-registered
provider (Twilio/MSG91) before any real deployment.
