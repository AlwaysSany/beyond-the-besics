from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Runtime settings, mostly sourced from environment variables."""

    debug: bool = False
    scheduler_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        debug = os.getenv("FLASK_DEBUG", "0") in {"1", "true", "True"}
        scheduler_enabled = os.getenv("SCHEDULER_ENABLED", "1") in {"1", "true", "True"}
        return cls(debug=debug, scheduler_enabled=scheduler_enabled)

    def as_flask_config(self) -> dict:
        return {
            "DEBUG": self.debug,
            "SCHEDULER_API_ENABLED": True,
        }

