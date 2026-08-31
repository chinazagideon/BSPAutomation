"""Pydantic v2 Schemas for Atomic Slot Reservations."""

from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class SlotHoldRequest(BaseModel):
    resource_id: UUID
    service_id: UUID
    customer_phone: str = "+2348031234567"
    start_time: datetime
    end_time: datetime
    hold_minutes: int = Field(10, ge=5, le=30)


class SlotHoldResponse(BaseModel):
    slot_id: UUID
    status: str
    resource_id: UUID
    service_id: UUID
    customer_phone: str
    start_time: datetime
    end_time: datetime
    hold_expires_at: datetime
    deposit_required_naira: float
    deposit_required_kobo: int

    model_config = {"from_attributes": True}
