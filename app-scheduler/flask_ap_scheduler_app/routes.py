from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from .scheduler import get_job_logs

api_bp = Blueprint("api", __name__)


@api_bp.route("/")
def index():
    """
    API Welcome and Help message
    ---
    responses:
      200:
        description: API description and list of endpoints
    """
    return jsonify(
        {
            "status": "running",
            "description": "Flask + APScheduler demo",
            "endpoints": {
                "GET /": "This help message",
                "GET /logs": "Recent job execution logs",
                "GET /jobs": "List all scheduled jobs",
                "POST /jobs/<id>/pause": "Pause a job",
                "POST /jobs/<id>/resume": "Resume a paused job",
            },
        }
    )


@api_bp.route("/logs")
def logs():
    """
    Get recent job execution logs
    ---
    responses:
      200:
        description: A list of recent logs from scheduled tasks
    """
    job_logs = get_job_logs()
    return jsonify({"count": len(job_logs), "logs": list(reversed(job_logs))})


@api_bp.route("/jobs")
def list_jobs():
    """
    List all scheduled jobs
    ---
    responses:
      200:
        description: A list of all currently registered jobs
    """
    scheduler = current_app.extensions.get("apscheduler")
    jobs = []
    if scheduler is not None:
        for job in scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "trigger": str(job.trigger),
                    "next_run": str(job.next_run_time),
                }
            )
    return jsonify({"jobs": jobs})


@api_bp.route("/jobs/<job_id>/pause", methods=["POST"])
def pause_job(job_id: str):
    """
    Pause a scheduled job
    ---
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: The ID of the job to pause
    responses:
      200:
        description: Job paused successfully
      503:
        description: Scheduler not running
    """
    scheduler = current_app.extensions.get("apscheduler")
    if scheduler is None:
        return jsonify({"error": "scheduler not running"}), 503
    scheduler.pause_job(job_id)
    return jsonify({"status": "paused", "job_id": job_id})


@api_bp.route("/jobs/<job_id>/resume", methods=["POST"])
def resume_job(job_id: str):
    """
    Resume a paused job
    ---
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: The ID of the job to resume
    responses:
      200:
        description: Job resumed successfully
      503:
        description: Scheduler not running
    """
    scheduler = current_app.extensions.get("apscheduler")
    if scheduler is None:
        return jsonify({"error": "scheduler not running"}), 503
    scheduler.resume_job(job_id)
    return jsonify({"status": "resumed", "job_id": job_id})
