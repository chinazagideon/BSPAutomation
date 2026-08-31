"""Pydantic v2 Schemas for Ingress Webhooks and NLU Classification."""

from typing import Optional, Dict, Any, List, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class WebhookMessageItem(BaseModel):
    id: str
    from_phone: str = Field(..., alias="from")
    text: Optional[Dict[str, str]] = None
    type: str = "text"
    timestamp: str


class WebhookPayload(BaseModel):
    object: str = "whatsapp_business_account"
    entry: List[Dict[str, Any]] = Field(default_factory=list)


class NLUClassificationRequest(BaseModel):
    message: str = Field(..., min_length=1)
    customer_phone: str = "+2348031234567"
    customer_name: Optional[str] = "Tunde Adeleke"
    previous_context: List[str] = Field(default_factory=list)


class NLUClassificationResponse(BaseModel):
    routing_source: Literal["FAST_PATH", "CUSTOM_LOCAL_MODEL", "GEMINI_LLM_ESCALATION", "FALLBACK_DESK_HANDOFF"]
    intent: str
    lead_tier: Literal["HOT", "WARM", "COLD"]
    urgency_score: int = Field(..., ge=1, le=10)
    confidence: float = Field(..., ge=0.0, le=1.0)
    detected_dialect: str
    suggested_reply: Optional[str] = None
    action: Optional[str] = None
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float
    tokens_consumed: int = 0
    estimated_kobo_saved: int = 0


class AIWalletRead(BaseModel):
    merchant_id: UUID
    balance_kobo: int
    balance_naira: float
    bundled_tokens_remaining: int
    total_tokens_consumed: int
    total_naira_saved: float
    is_active: bool

    model_config = {"from_attributes": True}
