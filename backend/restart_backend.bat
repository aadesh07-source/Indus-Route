@echo off
REM -------------------------------------------------------------------------
REM INDUS ROUTE — backend launcher (Twilio WhatsApp gateway)
REM -------------------------------------------------------------------------
REM Real credentials live in backend\.env (git-ignored). This batch file only
REM sets PYTHONPATH and starts uvicorn. Do NOT paste secrets here — GitHub
REM push protection will block the push.
REM
REM If you prefer to start the backend without .env, set the variables below
REM (copy the keys from backend\.env). Do NOT commit this file with real
REM values — use placeholders only.
REM -------------------------------------------------------------------------
pushd "C:\Users\Aadesh Darole\OneDrive\Desktop\Indus Route\backend"

set PYTHONPATH=C:\Users\Aadesh Darole\OneDrive\Desktop\Indus Route\backend
REM Twilio WhatsApp (INDUS ROUTE, WhatsApp-only). Set real values in
REM backend\.env — this batch file uses .env by default (no secrets here).

echo Starting backend with Twilio WhatsApp (INDUS ROUTE)...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning