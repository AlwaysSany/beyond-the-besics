from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from flask import Flask
from flask_apscheduler import APScheduler

_JOB_LOGS: List[Dict[str, Any]] = []


def get_job_logs() -> List[Dict[str, Any]]:
    return _JOB_LOGS


class SchedulerConfig:
    SCHEDULER_API_ENABLED = True


def create_scheduler(app: Flask) -> APScheduler:
    scheduler = APScheduler()
    app.config.from_object(SchedulerConfig)
    scheduler.init_app(app)

    @scheduler.task("interval", id="heartbeat", seconds=10, misfire_grace_time=5)
    def heartbeat():
        entry = {
            "time": datetime.now().isoformat(),
            "job": "heartbeat",
            "message": "💓 Heartbeat tick",
        }
        _JOB_LOGS.append(entry)
        print(entry["message"], entry["time"])

    @scheduler.task("interval", id="cleanup", seconds=30, misfire_grace_time=10)
    def cleanup():
        before = len(_JOB_LOGS)
        # Trim to last 50 entries
        _JOB_LOGS[:] = _JOB_LOGS[-50:]
        entry = {
            "time": datetime.now().isoformat(),
            "job": "cleanup",
            "message": f"🧹 Cleaned up logs ({before} → {len(_JOB_LOGS)} entries)",
        }
        _JOB_LOGS.append(entry)
        print(entry["message"])

    @scheduler.task("cron", id="hourly_report", minute=0, misfire_grace_time=60)
    def hourly_report():
        entry = {
            "time": datetime.now().isoformat(),
            "job": "hourly_report",
            "message": f"📊 Hourly report — {len(_JOB_LOGS)} log entries on record",
        }
        _JOB_LOGS.append(entry)
        print(entry["message"])

    return scheduler


def start_scheduler_if_enabled(app: Flask, scheduler: APScheduler, settings) -> None:
    if getattr(settings, "scheduler_enabled", True):
        if not scheduler.running:
            scheduler.start()
