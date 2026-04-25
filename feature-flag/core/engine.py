"""
Evaluation Engine

Evaluates feature flags against an EvaluationContext using a deterministic,
lock-free pipeline. The evaluation order is:

  1. Global kill switch (enabled=False)  → OFF
  2. Environment gating                  → OFF
  3. Explicit user targeting             → ON
  4. Group targeting                     → ON
  5. Rule group matching                 → ON / OFF
  6. Percentage rollout (via hash)       → ON / OFF
  7. Default (enabled flag, 100%)        → ON
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

from .models import EvaluationContext, EvaluationResult, FeatureFlag, Variant

if TYPE_CHECKING:
    pass


def _bucket(seed: str, flag_key: str) -> int:
    """
    Deterministically place a user+flag combination into a 0-99 bucket.
    Using the flag key in the hash ensures independent distribution across flags
    (a user in bucket 30 for flag A won't always be in bucket 30 for flag B).
    """
    raw = f"{seed}:{flag_key}".encode()
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:8], 16) % 100


def _assign_variant(variants: tuple[Variant, ...], seed: str, flag_key: str) -> Variant | None:
    """
    Consistently assign a user to a variant using weighted distribution.
    Variants are sorted by name for stability; weights must sum to ≤ 100.
    """
    if not variants:
        return None

    bucket = _bucket(seed, flag_key + ":variant")
    cumulative = 0
    for variant in sorted(variants, key=lambda v: v.name):
        cumulative += variant.weight
        if bucket < cumulative:
            return variant
    return None


def evaluate(flag: FeatureFlag, ctx: EvaluationContext) -> EvaluationResult:
    """
    Core evaluation function. Pure, stateless, and side-effect free.
    Returns an immutable EvaluationResult.
    """
    start = time.perf_counter()

    def result(enabled: bool, reason: str, variant: Variant | None = None) -> EvaluationResult:
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        return EvaluationResult(
            flag_key=flag.key,
            enabled=enabled,
            variant=variant.name if variant else None,
            payload=dict(variant.payload) if variant else {},
            reason=reason,
            evaluation_time_us=elapsed_us,
        )

    # ── 1. Global kill switch ────────────────────────────────────────────────
    if not flag.enabled:
        return result(False, "flag_disabled")

    # ── 2. Environment gating ────────────────────────────────────────────────
    if flag.environments and ctx.environment not in flag.environments:
        return result(False, f"env_not_targeted:{ctx.environment}")

    seed = ctx.user_id or ""

    # ── 3. Explicit user targeting ───────────────────────────────────────────
    if ctx.user_id and ctx.user_id in flag.target_users:
        variant = _assign_variant(flag.variants, seed, flag.key)
        return result(True, "user_targeted", variant)

    # ── 4. Group targeting ───────────────────────────────────────────────────
    if flag.target_groups and ctx.groups & flag.target_groups:
        matched_group = next(iter(ctx.groups & flag.target_groups))
        variant = _assign_variant(flag.variants, seed, flag.key)
        return result(True, f"group_targeted:{matched_group}", variant)

    # ── 5. Rule group evaluation ─────────────────────────────────────────────
    ctx_dict = ctx.to_dict()
    if flag.rule_groups:
        # All rule groups must pass (AND between groups)
        if not all(rg.evaluate(ctx_dict) for rg in flag.rule_groups):
            return result(False, "rules_not_matched")

    # ── 6. Percentage rollout ────────────────────────────────────────────────
    if flag.rollout_percentage < 100:
        if not seed:
            # No user identity → cannot deterministically bucket → OFF
            return result(False, "no_identity_for_rollout")
        bucket = _bucket(seed, flag.key)
        if bucket >= flag.rollout_percentage:
            return result(False, f"rollout_excluded:bucket={bucket}")

    # ── 7. Assign variant (if any) and return ON ─────────────────────────────
    variant = _assign_variant(flag.variants, seed, flag.key) if flag.variants else None
    return result(True, "default_on", variant)
