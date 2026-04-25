"""
Core data models for the feature flag system.
All models are immutable dataclasses to enable lock-free reads.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FlagType(str, Enum):
    RELEASE = "release"        # Deploy vs release decoupling
    EXPERIMENT = "experiment"  # A/B testing
    OPS = "ops"                # Kill switches / circuit breakers
    PERMISSION = "permission"  # User entitlements


class Operator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"


@dataclass(frozen=True)
class Rule:
    attribute: str
    operator: Operator
    value: Any

    def evaluate(self, context: dict[str, Any]) -> bool:
        ctx_value = context.get(self.attribute)
        if ctx_value is None:
            return False

        match self.operator:
            case Operator.EQUALS:
                return ctx_value == self.value
            case Operator.NOT_EQUALS:
                return ctx_value != self.value
            case Operator.IN:
                return ctx_value in self.value
            case Operator.NOT_IN:
                return ctx_value not in self.value
            case Operator.CONTAINS:
                return self.value in str(ctx_value)
            case Operator.STARTS_WITH:
                return str(ctx_value).startswith(str(self.value))
            case Operator.GREATER_THAN:
                return float(ctx_value) > float(self.value)
            case Operator.LESS_THAN:
                return float(ctx_value) < float(self.value)
            case _:
                return False


@dataclass(frozen=True)
class RuleGroup:
    """A group of rules combined with AND or OR logic."""
    rules: tuple[Rule, ...]
    match_all: bool = True  # True=AND, False=OR

    def evaluate(self, context: dict[str, Any]) -> bool:
        if not self.rules:
            return True
        if self.match_all:
            return all(r.evaluate(context) for r in self.rules)
        return any(r.evaluate(context) for r in self.rules)


@dataclass(frozen=True)
class Variant:
    """For A/B testing: a named variant with a weight."""
    name: str
    weight: int  # 0-100
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureFlag:
    key: str
    enabled: bool = False
    flag_type: FlagType = FlagType.RELEASE
    description: str = ""
    
    # Targeting
    target_users: frozenset[str] = field(default_factory=frozenset)
    target_groups: frozenset[str] = field(default_factory=frozenset)
    rule_groups: tuple[RuleGroup, ...] = field(default_factory=tuple)
    
    # Rollout
    rollout_percentage: int = 100  # 0-100
    
    # A/B Testing variants
    variants: tuple[Variant, ...] = field(default_factory=tuple)
    
    # Environments
    environments: frozenset[str] = field(default_factory=frozenset)
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class EvaluationContext:
    user_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    environment: str = "production"
    groups: frozenset[str] = field(default_factory=frozenset)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "environment": self.environment,
            "groups": list(self.groups),
            **self.attributes,
        }


@dataclass(frozen=True)
class EvaluationResult:
    flag_key: str
    enabled: bool
    variant: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    evaluation_time_us: float = 0.0
