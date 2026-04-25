"""
Flag Manager

The central orchestrator. Holds an immutable snapshot of all flags
(copy-on-write semantics) so reads are completely lock-free.

Write operations (add/update/delete) acquire a short write lock,
build a new snapshot dict, then atomically replace the reference.

Architecture decision: we use a threading.Lock only during writes.
Reads access `self._snapshot` which is a plain Python dict reference;
in CPython, dict reference assignment is atomic (single bytecode op).
For multi-interpreter safety or non-CPython runtimes, promote to
a RWLock or use a queue-based update model.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Iterator

from core.engine import evaluate
from core.models import (
    EvaluationContext, EvaluationResult, FeatureFlag, FlagType
)
from storage.store import FlagStore, InMemoryStore

logger = logging.getLogger(__name__)


class FlagManager:
    def __init__(self, store: FlagStore | None = None, fail_safe: bool = True):
        """
        Args:
            store:     persistence backend; defaults to InMemoryStore
            fail_safe: if True, return False (flag=off) on any evaluation error
        """
        self._store = store or InMemoryStore()
        self._fail_safe = fail_safe
        self._write_lock = threading.Lock()

        # Immutable snapshot; replaced atomically on every write
        self._snapshot: dict[str, FeatureFlag] = {}

        # Observers for flag change events
        self._observers: list[callable] = []

        # Evaluation audit log (last N evals per flag)
        self._audit: dict[str, list[EvaluationResult]] = {}
        self._audit_max = 100

        self.reload()
        self._store.watch(self.reload)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def reload(self) -> None:
        """Load flags from store and atomically swap the snapshot."""
        try:
            flags = self._store.load()
            with self._write_lock:
                self._snapshot = flags
            logger.info("Loaded %d flags", len(flags))
            self._notify_observers("reload", None)
        except Exception as e:
            logger.error("Failed to reload flags: %s", e)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def put(self, flag: FeatureFlag) -> None:
        """Insert or replace a flag, persisting to store."""
        with self._write_lock:
            new_snapshot = {**self._snapshot, flag.key: flag}
            self._store.save(new_snapshot)
            self._snapshot = new_snapshot
        self._notify_observers("put", flag.key)

    def delete(self, key: str) -> None:
        with self._write_lock:
            if key not in self._snapshot:
                raise KeyError(f"Flag not found: {key}")
            new_snapshot = {k: v for k, v in self._snapshot.items() if k != key}
            self._store.save(new_snapshot)
            self._snapshot = new_snapshot
        self._notify_observers("delete", key)

    def get(self, key: str) -> FeatureFlag | None:
        return self._snapshot.get(key)

    def all_flags(self) -> dict[str, FeatureFlag]:
        return dict(self._snapshot)

    def list_keys(self) -> list[str]:
        return list(self._snapshot.keys())

    # ── Evaluation ────────────────────────────────────────────────────────────

    def is_enabled(
        self,
        flag_key: str,
        ctx: EvaluationContext | None = None,
        *,
        default: bool = False,
    ) -> bool:
        """
        Simple boolean check. Uses default if flag is missing or on error.
        """
        result = self.evaluate(flag_key, ctx)
        if result is None:
            return default
        return result.enabled

    def evaluate(
        self,
        flag_key: str,
        ctx: EvaluationContext | None = None,
    ) -> EvaluationResult | None:
        """
        Full evaluation returning EvaluationResult with reason and variant info.
        Returns None if flag does not exist.
        """
        flag = self._snapshot.get(flag_key)
        if flag is None:
            logger.debug("Flag not found: %s", flag_key)
            return None

        ctx = ctx or EvaluationContext()

        try:
            result = evaluate(flag, ctx)
        except Exception as e:
            logger.error("Evaluation error for %s: %s", flag_key, e)
            if self._fail_safe:
                result = EvaluationResult(
                    flag_key=flag_key,
                    enabled=False,
                    reason=f"error:{e}",
                )
            else:
                raise

        self._record_audit(result)
        return result

    def evaluate_all(self, ctx: EvaluationContext | None = None) -> dict[str, EvaluationResult]:
        """Evaluate every flag for a given context."""
        ctx = ctx or EvaluationContext()
        return {key: self.evaluate(key, ctx) for key in self._snapshot}

    def get_variant(
        self,
        flag_key: str,
        ctx: EvaluationContext | None = None,
    ) -> str | None:
        result = self.evaluate(flag_key, ctx)
        return result.variant if result else None

    # ── Audit ─────────────────────────────────────────────────────────────────

    def _record_audit(self, result: EvaluationResult) -> None:
        log = self._audit.setdefault(result.flag_key, [])
        log.append(result)
        if len(log) > self._audit_max:
            log.pop(0)

    def audit_log(self, flag_key: str) -> list[EvaluationResult]:
        return list(self._audit.get(flag_key, []))

    # ── Observers ─────────────────────────────────────────────────────────────

    def subscribe(self, callback: callable) -> None:
        """Register a callback(event: str, flag_key: str | None) for flag changes."""
        self._observers.append(callback)

    def _notify_observers(self, event: str, flag_key: str | None) -> None:
        for cb in self._observers:
            try:
                cb(event, flag_key)
            except Exception as e:
                logger.error("Observer error: %s", e)

    # ── Convenience ───────────────────────────────────────────────────────────

    def flags_by_type(self, flag_type: FlagType) -> list[FeatureFlag]:
        return [f for f in self._snapshot.values() if f.flag_type == flag_type]

    def flags_by_tag(self, tag: str) -> list[FeatureFlag]:
        return [f for f in self._snapshot.values() if tag in f.tags]

    def __len__(self) -> int:
        return len(self._snapshot)

    def __contains__(self, key: str) -> bool:
        return key in self._snapshot

    def __iter__(self) -> Iterator[str]:
        return iter(self._snapshot)
