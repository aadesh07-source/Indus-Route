"""SLA / alert scheduling engine.

Uses APScheduler's BackgroundScheduler when available; otherwise falls back
to a plain daemon thread — so SLA monitoring always runs, never crashes the
app on a missing dependency, and stops cleanly on shutdown.
"""
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

from .. import db
from ..notifications.sms_gateway import queue_sms

_scheduler = None
_started = False

APPROACHING_WINDOW_DAYS = 2


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _already_notified(application_id: str, title: str, hours: int = 24) -> bool:
    cutoff = (_utcnow() - timedelta(hours=hours)).isoformat()
    row = db.query_one(
        "SELECT id FROM notifications WHERE application_id=? AND title=? AND created_at>=? LIMIT 1",
        (application_id, title, cutoff),
    )
    return row is not None


def sla_check_job() -> None:
    """Periodic job: SLA reminders, breach alerts, grievance flags."""
    try:
        apps = db.query(
            "SELECT a.id, a.status, a.sla_deadline, a.business_id, b.owner_id "
            "FROM applications a JOIN business_profiles b ON a.business_id=b.id "
            "WHERE a.status IN ('submitted','under_review','clarification_pending','provisionally_cleared') "
            "AND a.sla_deadline IS NOT NULL"
        )
        now = _utcnow()
        for app in apps:
            deadline = _parse_iso(app.get("sla_deadline"))
            if deadline is None:
                continue
            remaining = deadline - now
            if remaining.total_seconds() <= 0:
                if not _already_notified(app["id"], "SLA Breach Alert"):
                    db.execute(
                        "INSERT INTO notifications (id, user_id, application_id, channel, title, body, status, created_at) "
                        "VALUES (?,?,?,?,?,?, 'sent', ?)",
                        (db.new_id("ntf"), app["owner_id"], app["id"], "in_app+sms",
                         "SLA Breach Alert",
                         "Application {} has exceeded its SLA deadline. Escalated for priority review."
                         .format(app["id"]), _utcnow().isoformat()),
                    )
                    queue_sms("SLA breach on application {} — escalated for priority review."
                              .format(app["id"]), user_id=app["owner_id"], application_id=app["id"])
                    db.execute(
                        "INSERT INTO grievances (id, application_id, user_id, reason, description, "
                        "escalation_level, status, created_at) VALUES (?,?,?,?,?,1,'open',?)",
                        (db.new_id("grv"), app["id"], app["owner_id"], "SLA breach",
                         "Auto-raised by the SLA scheduler on deadline breach.", _utcnow().isoformat()),
                    )
            elif remaining <= timedelta(days=APPROACHING_WINDOW_DAYS):
                if not _already_notified(app["id"], "SLA Reminder"):
                    db.execute(
                        "INSERT INTO notifications (id, user_id, application_id, channel, title, body, status, created_at) "
                        "VALUES (?,?,?,?,?,?, 'sent', ?)",
                        (db.new_id("ntf"), app["owner_id"], app["id"], "in_app+sms",
                         "SLA Reminder",
                         "Application {} is approaching its SLA deadline ({}h remaining)."
                         .format(app["id"], max(0, int(remaining.total_seconds() // 3600))),
                         _utcnow().isoformat()),
                    )
                    queue_sms("Reminder: application {} is nearing its SLA deadline."
                              .format(app["id"]), user_id=app["owner_id"], application_id=app["id"])
    except Exception:
        traceback.print_exc()  # the scheduler must never take the API down


def _thread_loop(interval_seconds: int) -> None:
    while True:
        sla_check_job()
        time.sleep(interval_seconds)


def start_scheduler(interval_seconds: int = 60) -> dict:
    global _scheduler, _started
    if _started:
        return {"mode": "already-running"}
    _started = True
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore

        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(sla_check_job, "interval", seconds=interval_seconds,
                           id="sla_check", max_instances=1, coalesce=True)
        _scheduler.start()
        return {"mode": "apscheduler", "interval_seconds": interval_seconds}
    except ImportError:
        threading.Thread(target=_thread_loop, args=(interval_seconds,),
                         daemon=True, name="sla-check-fallback").start()
        return {"mode": "thread-fallback", "interval_seconds": interval_seconds}


def shutdown_scheduler() -> None:
    global _started
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    _started = False
