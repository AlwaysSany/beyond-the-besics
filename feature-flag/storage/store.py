"""
Storage Layer

Abstract base + concrete implementations:
  - InMemoryStore:  dict-backed, for tests and ephemeral configs
  - JsonFileStore:  file-backed with inotify/polling hot-reload
  - RedisStore:     Redis-backed for distributed setups (requires redis-py)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.models import (
    EvaluationContext, FeatureFlag, FlagType, Operator, Rule, RuleGroup, Variant
)

logger = logging.getLogger(__name__)


# ── Serialization helpers ────────────────────────────────────────────────────

def _flag_from_dict(key: str, d: dict[str, Any]) -> FeatureFlag:
    rule_groups = []
    for rg_data in d.get("rule_groups", []):
        rules = [
            Rule(
                attribute=r["attribute"],
                operator=Operator(r["operator"]),
                value=r["value"],
            )
            for r in rg_data.get("rules", [])
        ]
        rule_groups.append(RuleGroup(
            rules=tuple(rules),
            match_all=rg_data.get("match_all", True),
        ))

    variants = [
        Variant(
            name=v["name"],
            weight=v["weight"],
            payload=v.get("payload", {}),
        )
        for v in d.get("variants", [])
    ]

    return FeatureFlag(
        key=key,
        enabled=d.get("enabled", False),
        flag_type=FlagType(d.get("flag_type", "release")),
        description=d.get("description", ""),
        target_users=frozenset(d.get("target_users", [])),
        target_groups=frozenset(d.get("target_groups", [])),
        rule_groups=tuple(rule_groups),
        rollout_percentage=d.get("rollout_percentage", 100),
        variants=tuple(variants),
        environments=frozenset(d.get("environments", [])),
        tags=frozenset(d.get("tags", [])),
    )


def _flag_to_dict(flag: FeatureFlag) -> dict[str, Any]:
    return {
        "enabled": flag.enabled,
        "flag_type": flag.flag_type.value,
        "description": flag.description,
        "target_users": list(flag.target_users),
        "target_groups": list(flag.target_groups),
        "rule_groups": [
            {
                "match_all": rg.match_all,
                "rules": [
                    {"attribute": r.attribute, "operator": r.operator.value, "value": r.value}
                    for r in rg.rules
                ],
            }
            for rg in flag.rule_groups
        ],
        "rollout_percentage": flag.rollout_percentage,
        "variants": [
            {"name": v.name, "weight": v.weight, "payload": v.payload}
            for v in flag.variants
        ],
        "environments": list(flag.environments),
        "tags": list(flag.tags),
        "created_at": flag.created_at,
        "updated_at": flag.updated_at,
    }


# ── Abstract base ─────────────────────────────────────────────────────────────

class FlagStore(ABC):
    @abstractmethod
    def load(self) -> dict[str, FeatureFlag]: ...

    @abstractmethod
    def save(self, flags: dict[str, FeatureFlag]) -> None: ...

    def watch(self, callback: callable) -> None:
        """Optional: start watching for changes. Default: no-op."""


# ── In-memory store ───────────────────────────────────────────────────────────

class InMemoryStore(FlagStore):
    def __init__(self, initial: dict[str, Any] | None = None):
        self._data: dict[str, FeatureFlag] = {}
        if initial:
            for key, val in initial.items():
                self._data[key] = _flag_from_dict(key, val)

    def load(self) -> dict[str, FeatureFlag]:
        return dict(self._data)

    def save(self, flags: dict[str, FeatureFlag]) -> None:
        self._data = dict(flags)


# ── JSON file store ────────────────────────────────────────────────────────────

class JsonFileStore(FlagStore):
    def __init__(self, path: str | Path, poll_interval: float = 5.0):
        self.path = Path(path)
        self.poll_interval = poll_interval
        self._last_mtime: float = 0.0
        self._watcher_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def load(self) -> dict[str, FeatureFlag]:
        if not self.path.exists():
            logger.warning("Flag file not found: %s", self.path)
            return {}
        with open(self.path) as f:
            raw: dict[str, Any] = json.load(f)
        return {key: _flag_from_dict(key, val) for key, val in raw.items()}

    def save(self, flags: dict[str, FeatureFlag]) -> None:
        raw = {key: _flag_to_dict(flag) for key, flag in flags.items()}
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(raw, f, indent=2)
        tmp.replace(self.path)  # atomic on POSIX
        self._last_mtime = self.path.stat().st_mtime

    def watch(self, callback: callable) -> None:
        """Poll for file changes in a background daemon thread."""
        def _poll():
            while not self._stop_event.is_set():
                try:
                    if self.path.exists():
                        mtime = self.path.stat().st_mtime
                        if mtime != self._last_mtime:
                            self._last_mtime = mtime
                            logger.info("Flag file changed, reloading...")
                            callback()
                except Exception as e:
                    logger.error("Error watching flag file: %s", e)
                self._stop_event.wait(self.poll_interval)

        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._watcher_thread = threading.Thread(target=_poll, daemon=True, name="flag-watcher")
        self._watcher_thread.start()

    def stop_watching(self) -> None:
        self._stop_event.set()
