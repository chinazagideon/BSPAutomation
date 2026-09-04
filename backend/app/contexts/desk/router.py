"""FastAPI Router for Agent Desk Telemetry and Context Injection."""

from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

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


@router.post("/tickets/{ticket_id}/claim")
async def claim_escalation_ticket(
    ticket_id: UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Atomic Ticket Claim Guard (ADR-0036):
    Claims an unassigned ticket for the authenticated agent.
    Returns HTTP 200 on success, or HTTP 409 Conflict if already claimed.
    """
    from fastapi import HTTPException
    from app.contexts.desk.models import AgentProfile
    user_uuid = UUID(tenant.user_id) if tenant.user_id else None

    # Resolve agent profile ID for this user/merchant to satisfy foreign key
    profile_query = await db.execute(
        select(AgentProfile.id).where(
            AgentProfile.merchant_id == UUID(tenant.merchant_id),
            AgentProfile.user_id == user_uuid,
        )
    )
    agent_profile_id = profile_query.scalar_one_or_none()
    if not agent_profile_id:
        profile_query = await db.execute(
            select(AgentProfile.id).where(
                AgentProfile.merchant_id == UUID(tenant.merchant_id)
            ).limit(1)
        )
        agent_profile_id = profile_query.scalar_one_or_none()

    if not agent_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No registered agent profile found for this merchant",
        )

    ticket = await DeskService.claim_ticket(
        session=db,
        ticket_id=ticket_id,
        agent_id=agent_profile_id,
        merchant_id=UUID(tenant.merchant_id),
    )
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket already claimed by another agent or is no longer open",
        )
    return ApiResponse.create(
        data={
            "ticket_id": str(ticket.id),
            "status": ticket.status,
            "assigned_agent_id": str(ticket.assigned_agent_id),
        }
    )


@router.get("/agent/stream")
async def stream_desk_events(
    tenant: TenantContext = Depends(get_current_tenant),
):
    """
    Server-Sent Events (SSE) Streaming Endpoint (ADR-0036):
    Broadcasts live escalation tickets and handoff cards to online desk agents in real time.
    """
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    from app.contexts.desk.services import register_sse_client, unregister_sse_client

    queue = register_sse_client(tenant.merchant_id)

    async def event_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'status': 'STREAM_CONNECTED', 'merchant_id': tenant.merchant_id})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            unregister_sse_client(tenant.merchant_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

