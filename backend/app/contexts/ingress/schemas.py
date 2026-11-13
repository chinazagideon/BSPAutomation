"""Pydantic v2 Schemas for Ingress Webhooks and NLU Classification."""

import re
from typing import Optional, Dict, Any, List, Literal, Union
from uuid import UUID
from datetime import datetime
from pydantic import Field, field_validator

from app.core.response import CamelModel
from app.core.generation.ports import ExecutionPolicy

_DIVIDER_RE = re.compile(r"[━─]{3,}")


class DialogueTurn(CamelModel):
    """Role-attributed conversation turn for Stage 3 LLM context."""
    role: Literal["customer", "assistant"]
    text: str

    @field_validator("text", mode="before")
    @classmethod
    def _clean_ui_chrome(cls, v: Any) -> str:
        raw = str(v or "")
        cleaned = _DIVIDER_RE.sub("", raw)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


class WebhookMessageItem(CamelModel):
    id: str
    from_phone: str = Field(..., alias="from")
    text: Optional[Dict[str, str]] = None
    type: str = "text"
    timestamp: str


class WebhookPayload(CamelModel):
    object: str = "whatsapp_business_account"
    entry: List[Dict[str, Any]] = Field(default_factory=list)


class NLUClassificationRequest(CamelModel):
    message: str = Field(..., min_length=1)
    customer_phone: str = "+2348031234567"
    customer_name: Optional[str] = "Tunde Adeleke"
    previous_context: List[Union[DialogueTurn, str]] = Field(default_factory=list)
    policy: Optional[ExecutionPolicy] = Field(
        default=None,
        description="Optional execution policy override (e.g. DEEP_REASONING, FASTEST_PATH, LOCAL_MODEL, CASCADING_FALLBACK)",
    )


class NLUClassificationResponse(CamelModel):
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


class AIWalletRead(CamelModel):
    merchant_id: UUID
    balance_kobo: int
    balance_naira: float
    bundled_tokens_remaining: int
    total_tokens_consumed: int
    total_naira_saved: float
    is_active: bool

