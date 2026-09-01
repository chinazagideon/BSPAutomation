"""FastAPI Router for Agent Desk Telemetry and Context Injection."""

from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_tenant_db, get_current_tenant, TenantContext
from app.core.response import ApiResponse
from app.contexts.desk.schemas import (
    HeartbeatPingRequest,
    HeartbeatPingResponse,
    ContextInjectionRequest,
    ContextInjectionResponse,
)
from app.contexts.desk.services import DeskService

router = APIRouter(prefix="/desk", tags=["Agent Desk & Telemetry"])


@router.post("/heartbeat", response_model=ApiResponse[HeartbeatPingResponse])
async def agent_heartbeat_ping(
    payload: HeartbeatPingRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Records real-time agent heartbeat (<60s NEPA power / ISP failover threshold).
    """
    result = await DeskService.record_agent_heartbeat(
        session=db,
        merchant_id=UUID(tenant.merchant_id),
        request=payload,
    )
    return ApiResponse.create(data=result)


@router.post("/context", response_model=ApiResponse[ContextInjectionResponse])
async def generate_agent_context(payload: ContextInjectionRequest):
    """
    Synthesizes the 6-Field Context Card for zero-repeat human handoffs.
    """
    result = DeskService.generate_synthesized_context(payload)
    return ApiResponse.create(data=result)

