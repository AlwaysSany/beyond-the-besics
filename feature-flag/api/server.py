"""
FastAPI Admin API

REST endpoints for flag management and observability.
Mount this into a larger FastAPI app or run standalone.

Routes:
  GET    /flags              - list all flags
  GET    /flags/{key}        - get single flag
  POST   /flags              - create flag
  PUT    /flags/{key}        - update flag
  DELETE /flags/{key}        - delete flag
  POST   /flags/{key}/eval   - evaluate flag for a context
  GET    /flags/{key}/audit  - last N evaluations
  POST   /reload             - hot-reload from store
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.manager import FlagManager
from core.models import (
    EvaluationContext, FeatureFlag, FlagType, Rule, RuleGroup, Variant
)
from storage.store import JsonFileStore

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RuleSchema(BaseModel):
    attribute: str
    operator: str
    value: Any


class RuleGroupSchema(BaseModel):
    rules: list[RuleSchema] = []
    match_all: bool = True


class VariantSchema(BaseModel):
    name: str
    weight: int
    payload: dict[str, Any] = {}


class FlagCreateSchema(BaseModel):
    key: str
    enabled: bool = False
    flag_type: str = "release"
    description: str = ""
    rollout_percentage: int = Field(default=100, ge=0, le=100)
    target_users: list[str] = []
    target_groups: list[str] = []
    rule_groups: list[RuleGroupSchema] = []
    variants: list[VariantSchema] = []
    environments: list[str] = []
    tags: list[str] = []


class EvalContextSchema(BaseModel):
    user_id: str | None = None
    environment: str = "production"
    groups: list[str] = []
    attributes: dict[str, Any] = {}


# ── Paths ─────────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# ── App factory ───────────────────────────────────────────────────────────────

def create_app(manager: FlagManager) -> FastAPI:
    app = FastAPI(
        title="Flagsmith Admin API",
        description="Feature Flag Management",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── List flags ────────────────────────────────────────────────────────────

    @app.get("/flags")
    def list_flags(tag: str | None = None, flag_type: str | None = None):
        flags = manager.all_flags()
        if tag:
            flags = {k: v for k, v in flags.items() if tag in v.tags}
        if flag_type:
            flags = {k: v for k, v in flags.items() if v.flag_type.value == flag_type}
        return {
            "count": len(flags),
            "flags": {k: _serialize_flag(v) for k, v in flags.items()},
        }

    # ── Get single flag ───────────────────────────────────────────────────────

    @app.get("/flags/{key}")
    def get_flag(key: str):
        flag = manager.get(key)
        if not flag:
            raise HTTPException(status_code=404, detail=f"Flag '{key}' not found")
        return _serialize_flag(flag)

    # ── Create flag ───────────────────────────────────────────────────────────

    @app.post("/flags", status_code=201)
    def create_flag(body: FlagCreateSchema):
        if body.key in manager:
            raise HTTPException(status_code=409, detail=f"Flag '{body.key}' already exists")
        flag = _schema_to_flag(body)
        manager.put(flag)
        return _serialize_flag(flag)

    # ── Update flag ───────────────────────────────────────────────────────────

    @app.put("/flags/{key}")
    def update_flag(key: str, body: FlagCreateSchema):
        body.key = key
        flag = _schema_to_flag(body)
        manager.put(flag)
        return _serialize_flag(flag)

    # ── Delete flag ───────────────────────────────────────────────────────────

    @app.delete("/flags/{key}", status_code=204)
    def delete_flag(key: str):
        if key not in manager:
            raise HTTPException(status_code=404, detail=f"Flag '{key}' not found")
        manager.delete(key)
        return Response(status_code=204)

    # ── Evaluate flag ─────────────────────────────────────────────────────────

    @app.post("/flags/{key}/eval")
    def eval_flag(key: str, body: EvalContextSchema):
        ctx = EvaluationContext(
            user_id=body.user_id,
            environment=body.environment,
            groups=frozenset(body.groups),
            attributes=body.attributes,
        )
        result = manager.evaluate(key, ctx)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Flag '{key}' not found")
        return {
            "flag_key": result.flag_key,
            "enabled": result.enabled,
            "variant": result.variant,
            "payload": result.payload,
            "reason": result.reason,
            "evaluation_time_us": result.evaluation_time_us,
        }

    # ── Audit log ─────────────────────────────────────────────────────────────

    @app.get("/flags/{key}/audit")
    def audit_flag(key: str):
        if key not in manager:
            raise HTTPException(status_code=404, detail=f"Flag '{key}' not found")
        log = manager.audit_log(key)
        return {
            "flag_key": key,
            "count": len(log),
            "evaluations": [
                {
                    "enabled": r.enabled,
                    "variant": r.variant,
                    "reason": r.reason,
                    "evaluation_time_us": r.evaluation_time_us,
                }
                for r in log[-20:]  # last 20
            ],
        }

    # ── Hot reload ────────────────────────────────────────────────────────────

    @app.post("/reload")
    def reload_flags():
        manager.reload()
        return {"status": "ok", "count": len(manager)}

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health")
    def health():
        return {"status": "ok", "flag_count": len(manager), "ts": time.time()}

    # ── Frontend ──────────────────────────────────────────────────────────────

    @app.get("/", include_in_schema=False)
    def serve_frontend():
        """Serve the single-page admin dashboard."""
        return FileResponse(FRONTEND_DIR / "index.html")

    # Mount static assets (CSS/JS/images if added later)
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    return app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_flag(flag: FeatureFlag) -> dict:
    return {
        "key": flag.key,
        "enabled": flag.enabled,
        "flag_type": flag.flag_type.value,
        "description": flag.description,
        "rollout_percentage": flag.rollout_percentage,
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
        "variants": [
            {"name": v.name, "weight": v.weight, "payload": v.payload}
            for v in flag.variants
        ],
        "environments": list(flag.environments),
        "tags": list(flag.tags),
        "created_at": flag.created_at,
        "updated_at": flag.updated_at,
    }


def _schema_to_flag(body: FlagCreateSchema) -> FeatureFlag:
    from core.models import Operator as Op
    rule_groups = []
    for rg in body.rule_groups:
        rules = [Rule(attribute=r.attribute, operator=Op(r.operator), value=r.value) for r in rg.rules]
        rule_groups.append(RuleGroup(rules=tuple(rules), match_all=rg.match_all))

    variants = [Variant(name=v.name, weight=v.weight, payload=v.payload) for v in body.variants]

    return FeatureFlag(
        key=body.key,
        enabled=body.enabled,
        flag_type=FlagType(body.flag_type),
        description=body.description,
        rollout_percentage=body.rollout_percentage,
        target_users=frozenset(body.target_users),
        target_groups=frozenset(body.target_groups),
        rule_groups=tuple(rule_groups),
        variants=tuple(variants),
        environments=frozenset(body.environments),
        tags=frozenset(body.tags),
    )


# ── Standalone entrypoint ─────────────────────────────────────────────────────

def main():
    """Entry point for standalone server startup."""
    import uvicorn

    config_path = Path(__file__).resolve().parent.parent / "configs" / "flags.json"
    store = JsonFileStore(str(config_path))
    mgr = FlagManager(store=store)
    app = create_app(mgr)
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
