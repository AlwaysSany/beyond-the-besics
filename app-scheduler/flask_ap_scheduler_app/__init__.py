from __future__ import annotations

from flasgger import Swagger
from flask import Flask

from .config import Settings
from .routes import api_bp
from .scheduler import create_scheduler, start_scheduler_if_enabled


def create_app() -> Flask:
    app = Flask(__name__)
    settings = Settings.from_env()
    app.config.update(settings.as_flask_config())

    app.register_blueprint(api_bp)
    Swagger(app)

    scheduler = create_scheduler(app)
    app.extensions["apscheduler"] = scheduler
    start_scheduler_if_enabled(app, scheduler, settings=settings)

    return app
