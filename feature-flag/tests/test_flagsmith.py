"""
Test suite for the Flagsmith feature flag system.
Run with: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from core.engine import evaluate, _bucket
from core.manager import FlagManager
from core.models import (
    EvaluationContext, FeatureFlag, FlagType, Operator, Rule, RuleGroup, Variant
)
from storage.store import InMemoryStore, JsonFileStore


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def simple_flag():
    return FeatureFlag(key="test_flag", enabled=True)


@pytest.fixture
def manager():
    return FlagManager(store=InMemoryStore(), fail_safe=True)


@pytest.fixture
def ctx():
    return EvaluationContext(user_id="user_42", environment="production")


# ─── Engine: basic evaluation ─────────────────────────────────────────────────

class TestBasicEvaluation:
    def test_disabled_flag_returns_false(self):
        flag = FeatureFlag(key="f", enabled=False)
        ctx = EvaluationContext()
        result = evaluate(flag, ctx)
        assert result.enabled is False
        assert result.reason == "flag_disabled"

    def test_enabled_flag_returns_true(self):
        flag = FeatureFlag(key="f", enabled=True)
        result = evaluate(flag, EvaluationContext())
        assert result.enabled is True

    def test_result_has_flag_key(self, simple_flag, ctx):
        result = evaluate(simple_flag, ctx)
        assert result.flag_key == "test_flag"

    def test_evaluation_time_recorded(self, simple_flag, ctx):
        result = evaluate(simple_flag, ctx)
        assert result.evaluation_time_us >= 0


# ─── Engine: environment gating ──────────────────────────────────────────────

class TestEnvironmentGating:
    def test_flag_in_correct_env(self):
        flag = FeatureFlag(key="f", enabled=True, environments=frozenset(["staging"]))
        ctx = EvaluationContext(environment="staging")
        assert evaluate(flag, ctx).enabled is True

    def test_flag_blocked_in_wrong_env(self):
        flag = FeatureFlag(key="f", enabled=True, environments=frozenset(["staging"]))
        ctx = EvaluationContext(environment="production")
        result = evaluate(flag, ctx)
        assert result.enabled is False
        assert "env_not_targeted" in result.reason

    def test_no_env_restriction_allows_all(self):
        flag = FeatureFlag(key="f", enabled=True, environments=frozenset())
        for env in ["production", "staging", "dev", "anything"]:
            assert evaluate(flag, EvaluationContext(environment=env)).enabled is True


# ─── Engine: user targeting ───────────────────────────────────────────────────

class TestUserTargeting:
    def test_targeted_user_gets_flag(self):
        flag = FeatureFlag(
            key="f", enabled=True,
            target_users=frozenset(["alice"]),
            rollout_percentage=0,  # rollout off, but user targeted
        )
        ctx = EvaluationContext(user_id="alice")
        result = evaluate(flag, ctx)
        assert result.enabled is True
        assert result.reason == "user_targeted"

    def test_non_targeted_user_excluded_by_rollout(self):
        flag = FeatureFlag(
            key="f", enabled=True,
            target_users=frozenset(["alice"]),
            rollout_percentage=0,
        )
        ctx = EvaluationContext(user_id="bob")
        result = evaluate(flag, ctx)
        assert result.enabled is False


# ─── Engine: group targeting ──────────────────────────────────────────────────

class TestGroupTargeting:
    def test_group_member_gets_flag(self):
        flag = FeatureFlag(
            key="f", enabled=True,
            target_groups=frozenset(["beta_testers"]),
            rollout_percentage=0,
        )
        ctx = EvaluationContext(user_id="u1", groups=frozenset(["beta_testers"]))
        result = evaluate(flag, ctx)
        assert result.enabled is True
        assert "group_targeted" in result.reason

    def test_non_group_member_excluded(self):
        flag = FeatureFlag(
            key="f", enabled=True,
            target_groups=frozenset(["beta_testers"]),
            rollout_percentage=0,
        )
        ctx = EvaluationContext(user_id="u1", groups=frozenset(["regular_users"]))
        assert evaluate(flag, ctx).enabled is False


# ─── Engine: rule evaluation ──────────────────────────────────────────────────

class TestRuleEvaluation:
    def _make_flag(self, rules, match_all=True):
        rg = RuleGroup(rules=tuple(rules), match_all=match_all)
        return FeatureFlag(key="f", enabled=True, rule_groups=(rg,))

    def test_equals_rule_match(self):
        flag = self._make_flag([Rule("country", Operator.EQUALS, "US")])
        ctx = EvaluationContext(attributes={"country": "US"})
        assert evaluate(flag, ctx).enabled is True

    def test_equals_rule_no_match(self):
        flag = self._make_flag([Rule("country", Operator.EQUALS, "US")])
        ctx = EvaluationContext(attributes={"country": "UK"})
        assert evaluate(flag, ctx).enabled is False

    def test_in_operator(self):
        flag = self._make_flag([Rule("plan", Operator.IN, ["pro", "enterprise"])])
        assert evaluate(flag, EvaluationContext(attributes={"plan": "pro"})).enabled is True
        assert evaluate(flag, EvaluationContext(attributes={"plan": "free"})).enabled is False

    def test_not_in_operator(self):
        flag = self._make_flag([Rule("region", Operator.NOT_IN, ["CN", "RU"])])
        assert evaluate(flag, EvaluationContext(attributes={"region": "US"})).enabled is True
        assert evaluate(flag, EvaluationContext(attributes={"region": "CN"})).enabled is False

    def test_greater_than_operator(self):
        flag = self._make_flag([Rule("age", Operator.GREATER_THAN, 18)])
        assert evaluate(flag, EvaluationContext(attributes={"age": 25})).enabled is True
        assert evaluate(flag, EvaluationContext(attributes={"age": 15})).enabled is False

    def test_missing_attribute_returns_false(self):
        flag = self._make_flag([Rule("country", Operator.EQUALS, "US")])
        ctx = EvaluationContext(attributes={})
        assert evaluate(flag, ctx).enabled is False

    def test_or_rule_group(self):
        flag = self._make_flag([
            Rule("plan", Operator.EQUALS, "pro"),
            Rule("plan", Operator.EQUALS, "enterprise"),
        ], match_all=False)
        assert evaluate(flag, EvaluationContext(attributes={"plan": "pro"})).enabled is True
        assert evaluate(flag, EvaluationContext(attributes={"plan": "free"})).enabled is False


# ─── Engine: percentage rollout ───────────────────────────────────────────────

class TestPercentageRollout:
    def test_zero_percent_excludes_all(self):
        flag = FeatureFlag(key="f", enabled=True, rollout_percentage=0)
        for i in range(50):
            ctx = EvaluationContext(user_id=f"user_{i}")
            assert evaluate(flag, ctx).enabled is False

    def test_hundred_percent_includes_all(self):
        flag = FeatureFlag(key="f", enabled=True, rollout_percentage=100)
        for i in range(50):
            ctx = EvaluationContext(user_id=f"user_{i}")
            assert evaluate(flag, ctx).enabled is True

    def test_fifty_percent_roughly_half(self):
        flag = FeatureFlag(key="rollout_test", enabled=True, rollout_percentage=50)
        enabled_count = sum(
            1 for i in range(1000)
            if evaluate(flag, EvaluationContext(user_id=f"user_{i}")).enabled
        )
        # Within 5% of expected 500
        assert 450 <= enabled_count <= 550, f"Expected ~500 but got {enabled_count}"

    def test_deterministic_same_user_same_result(self):
        flag = FeatureFlag(key="f", enabled=True, rollout_percentage=50)
        ctx = EvaluationContext(user_id="consistent_user")
        results = {evaluate(flag, ctx).enabled for _ in range(10)}
        assert len(results) == 1  # Always same result

    def test_no_user_id_excluded_from_rollout(self):
        flag = FeatureFlag(key="f", enabled=True, rollout_percentage=50)
        result = evaluate(flag, EvaluationContext())  # no user_id
        assert result.enabled is False
        assert "no_identity_for_rollout" in result.reason

    def test_bucket_independence_across_flags(self):
        """Same user should get different buckets for different flags."""
        buckets = {_bucket("user_x", f"flag_{i}") for i in range(20)}
        assert len(buckets) > 1  # Not all the same


# ─── Engine: A/B variants ─────────────────────────────────────────────────────

class TestVariants:
    def test_variant_assigned_when_enabled(self):
        flag = FeatureFlag(
            key="ab_test",
            enabled=True,
            variants=(
                Variant("control", 50),
                Variant("treatment", 50),
            ),
        )
        ctx = EvaluationContext(user_id="user_1")
        result = evaluate(flag, ctx)
        assert result.enabled is True
        assert result.variant in ("control", "treatment")

    def test_same_user_same_variant(self):
        flag = FeatureFlag(
            key="ab_test",
            enabled=True,
            variants=(
                Variant("control", 50),
                Variant("treatment", 50),
            ),
        )
        ctx = EvaluationContext(user_id="stable_user")
        variants = {evaluate(flag, ctx).variant for _ in range(10)}
        assert len(variants) == 1

    def test_variant_payload_returned(self):
        flag = FeatureFlag(
            key="ab_test",
            enabled=True,
            variants=(Variant("v_a", 100, payload={"color": "blue"}),),
        )
        result = evaluate(flag, EvaluationContext(user_id="u1"))
        assert result.variant == "v_a"
        assert result.payload == {"color": "blue"}

    def test_variant_distribution(self):
        flag = FeatureFlag(
            key="split_test",
            enabled=True,
            variants=(
                Variant("control", 70),
                Variant("treatment", 30),
            ),
        )
        counts = {"control": 0, "treatment": 0}
        for i in range(1000):
            r = evaluate(flag, EvaluationContext(user_id=f"u{i}"))
            counts[r.variant] += 1
        # control ~70%, treatment ~30% within 8%
        assert 620 <= counts["control"] <= 780
        assert 220 <= counts["treatment"] <= 380


# ─── FlagManager ─────────────────────────────────────────────────────────────

class TestFlagManager:
    def test_put_and_get(self, manager):
        flag = FeatureFlag(key="my_flag", enabled=True)
        manager.put(flag)
        retrieved = manager.get("my_flag")
        assert retrieved is not None
        assert retrieved.key == "my_flag"

    def test_delete_flag(self, manager):
        flag = FeatureFlag(key="to_delete", enabled=True)
        manager.put(flag)
        manager.delete("to_delete")
        assert manager.get("to_delete") is None

    def test_delete_nonexistent_raises(self, manager):
        with pytest.raises(KeyError):
            manager.delete("nonexistent")

    def test_is_enabled_missing_flag_returns_default(self, manager, ctx):
        assert manager.is_enabled("ghost_flag", ctx, default=False) is False
        assert manager.is_enabled("ghost_flag", ctx, default=True) is True

    def test_evaluate_missing_flag_returns_none(self, manager, ctx):
        assert manager.evaluate("ghost_flag", ctx) is None

    def test_fail_safe_returns_false_on_error(self):
        bad_store = InMemoryStore()
        mgr = FlagManager(store=bad_store, fail_safe=True)
        # Manually inject a broken flag (won't happen in normal usage)
        flag = FeatureFlag(key="broken", enabled=True)
        mgr._snapshot = {"broken": flag}
        # Monkey-patch engine to raise
        import core.manager as cm
        original = cm.evaluate
        cm.evaluate = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        result = mgr.evaluate("broken", EvaluationContext())
        cm.evaluate = original
        assert result.enabled is False

    def test_contains(self, manager):
        manager.put(FeatureFlag(key="exists", enabled=True))
        assert "exists" in manager
        assert "missing" not in manager

    def test_len(self, manager):
        for i in range(3):
            manager.put(FeatureFlag(key=f"flag_{i}", enabled=True))
        assert len(manager) == 3

    def test_audit_log_records_evaluations(self, manager):
        flag = FeatureFlag(key="audited", enabled=True)
        manager.put(flag)
        ctx = EvaluationContext(user_id="u1")
        for _ in range(5):
            manager.evaluate("audited", ctx)
        log = manager.audit_log("audited")
        assert len(log) == 5

    def test_observer_called_on_put(self, manager):
        events = []
        manager.subscribe(lambda event, key: events.append((event, key)))
        manager.put(FeatureFlag(key="watched", enabled=True))
        assert ("put", "watched") in events

    def test_evaluate_all(self, manager):
        for i in range(3):
            manager.put(FeatureFlag(key=f"f{i}", enabled=True))
        ctx = EvaluationContext(user_id="u1")
        results = manager.evaluate_all(ctx)
        assert len(results) == 3
        assert all(r.enabled for r in results.values())

    def test_thread_safety(self, manager):
        """Concurrent writes and reads should not cause data corruption."""
        errors = []

        def writer():
            try:
                for i in range(50):
                    manager.put(FeatureFlag(key=f"flag_{i}", enabled=True))
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(200):
                    _ = manager.all_flags()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Thread safety errors: {errors}"


# ─── Storage: JsonFileStore ───────────────────────────────────────────────────

class TestJsonFileStore:
    def test_save_and_load_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name

        store = JsonFileStore(path)
        flags = {
            "my_flag": FeatureFlag(
                key="my_flag",
                enabled=True,
                rollout_percentage=75,
                tags=frozenset(["beta"]),
            )
        }
        store.save(flags)
        loaded = store.load()
        assert "my_flag" in loaded
        assert loaded["my_flag"].enabled is True
        assert loaded["my_flag"].rollout_percentage == 75
        assert "beta" in loaded["my_flag"].tags
        Path(path).unlink()

    def test_load_missing_file_returns_empty(self, tmp_path):
        store = JsonFileStore(tmp_path / "nonexistent.json")
        assert store.load() == {}

    def test_hot_reload_via_callback(self, tmp_path):
        path = tmp_path / "flags.json"
        path.write_text("{}")

        store = JsonFileStore(str(path), poll_interval=0.1)
        reload_count = [0]

        def on_reload():
            reload_count[0] += 1

        store.watch(on_reload)
        time.sleep(0.05)

        # Modify file
        path.write_text(json.dumps({"new_flag": {"enabled": True}}))
        time.sleep(0.3)  # Wait for poll

        store.stop_watching()
        assert reload_count[0] >= 1


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_target_users(self):
        flag = FeatureFlag(key="f", enabled=True, target_users=frozenset())
        assert evaluate(flag, EvaluationContext(user_id="anyone")).enabled is True

    def test_empty_rule_groups(self):
        flag = FeatureFlag(key="f", enabled=True, rule_groups=())
        assert evaluate(flag, EvaluationContext()).enabled is True

    def test_variants_with_no_user_id(self):
        flag = FeatureFlag(
            key="ab",
            enabled=True,
            variants=(Variant("v1", 100),),
        )
        # No user_id means seed="" — should still assign a variant
        result = evaluate(flag, EvaluationContext())
        # rollout is 100 so identity check is skipped; variant gets seed=""
        assert result.variant == "v1"

    def test_contains_operator(self):
        rule = Rule("email", Operator.CONTAINS, "@company.com")
        flag = FeatureFlag(key="f", enabled=True, rule_groups=(RuleGroup(rules=(rule,)),))
        assert evaluate(flag, EvaluationContext(attributes={"email": "alice@company.com"})).enabled is True
        assert evaluate(flag, EvaluationContext(attributes={"email": "bob@gmail.com"})).enabled is False
