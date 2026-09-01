"""Pydantic v2 Schemas for Compliance, PII Sanitization, and Chained Consent."""

from typing import List, Dict, Optional, Literal
from uuid import UUID
from datetime import datetime
from pydantic import Field

from app.core.response import CamelModel


class RedactedEntity(CamelModel):
    type: Literal["BVN", "NIN", "NUBAN", "CARD_PAN", "PHONE"]
    value: str
    token: str


class PiiSanitizeRequest(CamelModel):
    text: str = Field(..., min_length=1)


class PiiSanitizeResponse(CamelModel):
    original_text: str
    sanitized_text: str
    redacted_entities: List[RedactedEntity]
    safety_score: int


class ConsentLogRequest(CamelModel):
    customer_phone: str = "+2348031234567"
    action: Literal["OPT_IN", "OPT_OUT_STOP", "OPT_OUT_COMOT", "EXPLICIT_REVOCATION"]
    channel: str = "WHATSAPP"


class ConsentEventRead(CamelModel):
    id: UUID
    merchant_id: UUID
    customer_phone: str
    action: str
    channel: str
    previous_event_hash: Optional[str] = None
    immutable_hash: str
    created_at: datetime

