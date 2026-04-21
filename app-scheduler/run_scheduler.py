from flask_ap_scheduler_app import create_app
from flask_ap_scheduler_app.scheduler import start_scheduler_if_enabled


def main() -> None:
    app = create_app()
    scheduler = app.extensions.get("apscheduler")
    if scheduler is None:
        raise RuntimeError("Scheduler extension not found on app")
    # Force-enable scheduler for this process
    class _Settings:
        scheduler_enabled = True

    start_scheduler_if_enabled(app, scheduler, settings=_Settings())


if __name__ == "__main__":
    main()

