"""
Policy management endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.admin_auth import require_admin_token
from core import audit, memory, policy

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/policy",
    tags=["policy"],
    dependencies=[Depends(require_admin_token)],
)


class PolicyRuleUpdateRequest(BaseModel):
    enabled: bool


class PolicyRuleUpsertRequest(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    pattern: str = Field(min_length=1)
    action: str = Field(default="block", min_length=1)
    description: str = Field(default="")
    enabled: bool = True
    priority: int = Field(default=100)


@router.get("/rules")
async def get_policy_rules() -> dict:
    return {"rules": policy.get_policy_rules_snapshot()}


@router.get("/status")
async def get_policy_status() -> dict:
    return policy.get_policy_status()


@router.put("/rules/{rule_id}")
async def set_policy_rule_enabled(rule_id: str, req: PolicyRuleUpdateRequest) -> dict:
    existing = await memory.get_policy_rule(rule_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Policy rule {rule_id!r} not found")

    updated = await memory.upsert_policy_rule(
        rule_id=existing["id"],
        name=existing["name"],
        scope=existing["scope"],
        pattern=existing["pattern"],
        action=existing["action"],
        description=existing["description"],
        enabled=req.enabled,
        priority=existing["priority"],
    )
    await policy.refresh_policy_cache()
    await audit.log_event(
        agent_id="system",
        event_type="policy_rule_updated",
        details={
            "rule_id": updated["id"],
            "enabled": updated["enabled"],
        },
    )
    return {"rule": updated}


@router.post("/rules")
async def upsert_policy_rule(req: PolicyRuleUpsertRequest) -> dict:
    updated = await memory.upsert_policy_rule(
        rule_id=req.id,
        name=req.name,
        scope=req.scope,
        pattern=req.pattern,
        action=req.action,
        description=req.description,
        enabled=req.enabled,
        priority=req.priority,
    )
    await policy.refresh_policy_cache()
    await audit.log_event(
        agent_id="system",
        event_type="policy_rule_created",
        details={
            "rule_id": updated["id"],
            "scope": updated["scope"],
        },
    )
    logger.info("Policy rule %s upserted", updated["id"])
    return {"rule": updated}


@router.post("/sync")
async def sync_policy_engine() -> dict:
    result = await policy.sync_opa_bundle()
    await audit.log_event(
        agent_id="system",
        event_type="policy_engine_synced",
        details=result,
    )
    return result
