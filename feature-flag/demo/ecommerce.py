"""
Demo: E-Commerce API with Feature Flags

Simulates an order processing service using feature flags for:
  1. New recommendation engine (release toggle, 25% rollout)
  2. New checkout UI (A/B test: control vs streamlined)
  3. Discount feature (permission toggle: pro users only)
  4. Emergency payment kill switch (ops toggle)

Run: python demo/ecommerce.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import time

from sdk.client import Context, FlagsmithClient
from core.models import FeatureFlag, FlagType, Rule, RuleGroup, Variant, Operator


def setup_client() -> FlagsmithClient:
    client = FlagsmithClient(fail_safe=True)

    # ── Flag 1: New recommendation engine (25% rollout) ───────────────────
    client.create_flag(
        key="new_recommendation_engine",
        enabled=True,
        flag_type="release",
        description="ML-powered recommendations. Rolling out to 25% of users.",
        rollout_percentage=25,
        tags=["ml", "recommendations"],
    )

    # ── Flag 2: Checkout A/B test ─────────────────────────────────────────
    client.create_flag(
        key="checkout_flow",
        enabled=True,
        flag_type="experiment",
        description="A/B test: control (3-step) vs streamlined (1-step) checkout",
        rollout_percentage=100,
        variants=[
            {"name": "control",      "weight": 50, "payload": {"steps": 3}},
            {"name": "streamlined",  "weight": 50, "payload": {"steps": 1}},
        ],
        tags=["checkout", "ab-test"],
    )

    # ── Flag 3: Pro user discount ─────────────────────────────────────────
    # Only enabled for users with plan=pro or plan=enterprise
    from core.models import FeatureFlag as FF, RuleGroup as RG, Rule as R, Operator as Op
    from core.manager import FlagManager
    from storage.store import InMemoryStore

    discount_flag = FF(
        key="loyalty_discount",
        enabled=True,
        flag_type=FlagType.PERMISSION,
        description="10% loyalty discount for pro/enterprise users",
        rule_groups=(
            RG(
                rules=(R("plan", Op.IN, ["pro", "enterprise"]),),
                match_all=True,
            ),
        ),
        tags=["billing", "discount"],
    )
    client._manager.put(discount_flag)

    # ── Flag 4: Payment kill switch ────────────────────────────────────────
    client.create_flag(
        key="payment_processing",
        enabled=True,
        flag_type="ops",
        description="KILL SWITCH: disable if payment provider is down",
        rollout_percentage=100,
        tags=["payments", "critical"],
    )

    return client


def simulate_request(client: FlagsmithClient, user_id: str, plan: str, region: str):
    ctx = Context(
        user_id=user_id,
        plan=plan,
        region=region,
        environment="production",
    )

    print(f"\n{'─'*60}")
    print(f"  User: {user_id}  |  Plan: {plan}  |  Region: {region}")
    print(f"{'─'*60}")

    # 1. Recommendation engine
    if client.is_enabled("new_recommendation_engine", ctx=ctx):
        print("  🤖 Recommendations: ML-powered engine")
    else:
        print("  📋 Recommendations: legacy rule-based engine")

    # 2. Checkout variant
    variant = client.get_variant("checkout_flow", ctx=ctx)
    result = client.evaluate("checkout_flow", ctx=ctx)
    steps = result.payload.get("steps", "?") if result else "?"
    print(f"  🛒 Checkout: variant='{variant}' ({steps} steps)")

    # 3. Discount
    if client.is_enabled("loyalty_discount", ctx=ctx):
        print("  💳 Discount: 10% loyalty discount applied ✓")
    else:
        print("  💳 Discount: not eligible")

    # 4. Kill switch
    if client.is_enabled("payment_processing", ctx=ctx):
        print("  💰 Payment: processing enabled ✓")
    else:
        print("  🚨 Payment: DISABLED — show maintenance message")


def demo_kill_switch(client: FlagsmithClient):
    print("\n\n" + "═"*60)
    print("  DEMO: Emergency Kill Switch — disabling payment processing")
    print("═"*60)

    # Simulate turning off the payment flag (e.g., payment provider is down)
    from core.models import FeatureFlag
    flag = client.list_flags().get("payment_processing")
    if flag:
        # Replace with disabled version (immutable model)
        import dataclasses
        disabled = dataclasses.replace(flag, enabled=False)
        client._manager.put(disabled)

    ctx = Context(user_id="alice", plan="pro", region="US")
    enabled = client.is_enabled("payment_processing", ctx=ctx)
    print(f"  payment_processing flag: {'ON' if enabled else 'OFF'}")
    print("  → All users now see maintenance page until flag is re-enabled")


def demo_audit_log(client: FlagsmithClient):
    print("\n\n" + "═"*60)
    print("  DEMO: Audit Log — why was checkout_flow evaluated?")
    print("═"*60)

    log = client.audit_log("checkout_flow")
    for entry in log[-5:]:
        print(f"  enabled={entry.enabled}  variant={entry.variant:<15} reason={entry.reason}")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║       Flagsmith Demo — E-Commerce Feature Flags      ║")
    print("╚══════════════════════════════════════════════════════╝")

    client = setup_client()

    users = [
        ("user_001", "free",       "US"),
        ("user_002", "pro",        "US"),
        ("user_003", "enterprise", "EU"),
        ("user_004", "free",       "EU"),
        ("user_005", "pro",        "APAC"),
        ("user_006", "free",       "US"),
        ("user_007", "enterprise", "US"),
    ]

    for uid, plan, region in users:
        simulate_request(client, uid, plan, region)

    demo_kill_switch(client)
    demo_audit_log(client)

    print("\n\n✓ Demo complete.\n")
