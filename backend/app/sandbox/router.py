"""Thin FastAPI Router for the Local BSP Sandbox Control Plane, delegating to SandboxOrchestrationService (ADR-0047)."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from app.sandbox.schemas import (
    SandboxBurstRequest,
    SandboxInboundRequest,
    SandboxTemplateSendRequest,
)
from app.sandbox.service import SandboxOrchestrationService
from app.sandbox.state import get_sandbox_store

router = APIRouter(prefix="/sandbox", tags=["Local BSP Sandbox & Fault Injection"])


@router.post("/waba/{phone_number_id}/messages", status_code=status.HTTP_200_OK)
async def sandbox_graph_messages_endpoint(phone_number_id: str, request: Request):
    """Wire-level Meta Graph API v20.0 Loopback Endpoint for AuditedHttpClient."""
    body = await request.json()
    return await SandboxOrchestrationService.handle_loopback_graph_egress(phone_number_id, body)


@router.get("/state")
async def get_sandbox_state(
    phone_number_id: str = "meta_phone_alaba_agro",
    customer_phone: str = "2348031234567",
):
    """Returns full Local BSP Sandbox state snapshot."""
    return await SandboxOrchestrationService.get_state_snapshot(phone_number_id, customer_phone)


@router.post("/inbound")
async def dispatch_sandbox_inbound(req: SandboxInboundRequest, request: Request):
    """Signs and dispatches an inbound webhook turn through the ingress & worker pipeline."""
    return await SandboxOrchestrationService.dispatch_inbound_turn(req, app_state=request.app.state)


@router.post("/burst")
async def dispatch_sandbox_message_burst(req: SandboxBurstRequest, request: Request):
    """Fires concurrent staggered customer messages to test the 1.2s burst debounce window."""
    return await SandboxOrchestrationService.dispatch_burst(req, app_state=request.app.state)


@router.patch("/faults")
async def update_sandbox_fault_profile(updates: Dict[str, Any]):
    """Updates runtime fault injection and 24h window clock offset rules."""
    profile = await get_sandbox_store().update_fault_profile(updates)
    return {"status": "UPDATED", "fault_profile": profile.model_dump()}


@router.patch("/nlu-controller")
async def update_sandbox_nlu_controller(updates: Dict[str, Any]):
    """Updates runtime NLU stage toggles (`use_fast_path`, `use_custom_model`, `use_llm_escalation`)."""
    ctrl = await get_sandbox_store().update_nlu_controller(updates)
    return {"status": "UPDATED", "nlu_controller": ctrl.model_dump()}


@router.post("/send-template")
async def send_sandbox_template_message(req: SandboxTemplateSendRequest, request: Request):
    """Dispatches a pre-approved WhatsApp Business Template (allowed even when 24h window is expired)."""
    return await SandboxOrchestrationService.send_template(req, app_state=request.app.state)


@router.post("/reset")
async def reset_sandbox_session(
    phone_number_id: str = "meta_phone_alaba_agro",
    customer_phone: str = "2348031234567",
):
    """Clears sandbox chat history, evicts active NegotiationFrame, and resets fault profile."""
    return await SandboxOrchestrationService.reset_session(phone_number_id, customer_phone)


@router.delete("/telemetry")
async def clear_sandbox_telemetry():
    """Clears the real-time telemetry buffer."""
    await get_sandbox_store().clear_telemetry()
    return {"status": "CLEARED"}


@router.get("/stream")
async def sandbox_sse_stream(request: Request):
    """Streams real-time outbound WhatsApp messages, webhook logs, and NLU traces to the React WebUI."""
    store = get_sandbox_store()
    queue = store.subscribe_sse()

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            store.unsubscribe_sse(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
