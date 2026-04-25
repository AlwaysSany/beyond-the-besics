"""
Flagsmith Python SDK

Provides a clean, minimal interface for application code.
Supports both functional and decorator-based usage.

Usage:
    from sdk.client import FlagsmithClient, Context

    client = FlagsmithClient(config_file="flags.json")

    # Simple boolean
    if client.is_enabled("dark_mode", user_id="u123"):
        ...

    # Context-aware
    ctx = Context(user_id="u123", region="US", plan="pro")
    if client.is_enabled("new_dashboard", ctx=ctx):
        ...

    # Variant / A-B testing
    variant = client.get_variant("checkout_flow", ctx=ctx)
    match variant:
        case "control": ...
        case "variant_a": ...

    # Decorator
    @client.feature("beta_export", default=lambda *a, **kw: None)
    def export_csv(data):
        ...
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from core.manager import FlagManager
from core.models import EvaluationContext, FeatureFlag, FlagType, Rule, RuleGroup, Variant
from storage.store import InMemoryStore, JsonFileStore

logger = logging.getLogger(__name__)


class Context:
    """Convenience wrapper around EvaluationContext."""
    def __init__(self, user_id: str | None = None, environment: str = "production", **attributes: Any):
        self.user_id = user_id
        self.environment = environment
        self.attributes = attributes
        self.groups: frozenset[str] = frozenset(attributes.pop("groups", []))

    def _to_eval_ctx(self) -> EvaluationContext:
        return EvaluationContext(
            user_id=self.user_id,
            environment=self.environment,
            attributes=self.attributes,
            groups=self.groups,
        )


class FlagsmithClient:
    def __init__(
        self,
        config_file: str | None = None,
        initial_flags: dict[str, Any] | None = None,
        fail_safe: bool = True,
        poll_interval: float = 10.0,
    ):
        if config_file:
            store = JsonFileStore(config_file, poll_interval=poll_interval)
        else:
            store = InMemoryStore(initial_flags or {})

        self._manager = FlagManager(store=store, fail_safe=fail_safe)

    # ── Core API ──────────────────────────────────────────────────────────────

    def is_enabled(
        self,
        flag_key: str,
        ctx: Context | None = None,
        user_id: str | None = None,
        default: bool = False,
        **attributes: Any,
    ) -> bool:
        eval_ctx = self._build_ctx(ctx, user_id, attributes)
        return self._manager.is_enabled(flag_key, eval_ctx, default=default)

    def get_variant(
        self,
        flag_key: str,
        ctx: Context | None = None,
        user_id: str | None = None,
        **attributes: Any,
    ) -> str | None:
        eval_ctx = self._build_ctx(ctx, user_id, attributes)
        return self._manager.get_variant(flag_key, eval_ctx)

    def evaluate(self, flag_key: str, ctx: Context | None = None, **kw):
        eval_ctx = self._build_ctx(ctx, kw.pop("user_id", None), kw)
        return self._manager.evaluate(flag_key, eval_ctx)

    # ── Decorator ─────────────────────────────────────────────────────────────

    def feature(
        self,
        flag_key: str,
        default: Any = None,
        ctx_arg: str | None = None,
    ) -> Callable:
        """
        Decorator that gates a function behind a feature flag.
        If the flag is off, returns `default` (or calls it if callable).

        @client.feature("new_search")
        def search(query, user_id):
            ...

        If ctx_arg is given, reads the Context from that kwarg name.
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                ctx = kwargs.get(ctx_arg) if ctx_arg else None
                if isinstance(ctx, Context):
                    enabled = self.is_enabled(flag_key, ctx=ctx)
                else:
                    enabled = self.is_enabled(flag_key)

                if not enabled:
                    return default(*args, **kwargs) if callable(default) else default
                return func(*args, **kwargs)
            return wrapper
        return decorator

    # ── Management ────────────────────────────────────────────────────────────

    def create_flag(
        self,
        key: str,
        enabled: bool = False,
        flag_type: str = "release",
        description: str = "",
        rollout_percentage: int = 100,
        target_users: list[str] | None = None,
        environments: list[str] | None = None,
        tags: list[str] | None = None,
        variants: list[dict] | None = None,
    ) -> FeatureFlag:
        """Programmatically create and register a flag."""
        parsed_variants = tuple(
            Variant(name=v["name"], weight=v["weight"], payload=v.get("payload", {}))
            for v in (variants or [])
        )
        flag = FeatureFlag(
            key=key,
            enabled=enabled,
            flag_type=FlagType(flag_type),
            description=description,
            rollout_percentage=rollout_percentage,
            target_users=frozenset(target_users or []),
            environments=frozenset(environments or []),
            tags=frozenset(tags or []),
            variants=parsed_variants,
        )
        self._manager.put(flag)
        return flag

    def delete_flag(self, key: str) -> None:
        self._manager.delete(key)

    def list_flags(self) -> dict[str, FeatureFlag]:
        return self._manager.all_flags()

    def reload(self) -> None:
        self._manager.reload()

    def audit_log(self, flag_key: str):
        return self._manager.audit_log(flag_key)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _build_ctx(
        self,
        ctx: Context | None,
        user_id: str | None,
        attributes: dict,
    ) -> EvaluationContext:
        if ctx is not None:
            return ctx._to_eval_ctx()
        return EvaluationContext(
            user_id=user_id,
            attributes=attributes,
        )
