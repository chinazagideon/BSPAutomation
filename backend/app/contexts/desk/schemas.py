"""Pydantic v2 Schemas for Agent Desk & 6-Field Context Card."""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import Field

from app.core.response import CamelModel


class HeartbeatPingRequest(CamelModel):
    agent_id: UUID
    ip_address: Optional[str] = "102.89.41.12"
    latency_ms: int = Field(24, ge=1)


class HeartbeatPingResponse(CamelModel):
    agent_id: UUID
    status: str
    last_heartbeat_at: datetime
    nepa_offline_threshold_seconds: int = 60


class ContextInjectionRequest(CamelModel):
    customer_name: str = "Chidinma Okafor"
    customer_phone: str = "+2348023456789"
    chat_history: List[str] = Field(default_factory=list)


class SixFieldContextCard(CamelModel):
    """The 6-field synthesized context card injected into live agent interface."""
    executive_summary: str = Field(..., description="1-2 sentence core intent summary")
    detected_budget_naira: str = Field(..., description="Estimated customer budget")
    urgency_tier: str = Field(..., description="HOT, WARM, COLD")
    dialect: str = Field(..., description="Detected dialect")
    key_blockers: str = Field(..., description="Delivery, pricing, or payment friction")
    suggested_first_response: str = Field(..., description="Exact zero-repeat conversational opener")


class ContextInjectionResponse(CamelModel):
    status: str = "CONTEXT_INJECTED"
    agent_hub: str = "Ikeja Tech Support Hub 01"
    customer: dict
    summary: SixFieldContextCard

