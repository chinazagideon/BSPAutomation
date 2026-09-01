"""Pydantic v2 Schemas for Checkout & 4-Leg Double Entry Ledger."""

from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime
from pydantic import Field

from app.core.response import CamelModel


class CartItemInput(CamelModel):
    item_sku: str
    item_title: str
    unit_price_kobo: int = Field(..., gt=0)
    quantity: int = Field(1, ge=1)


class CartCreateRequest(CamelModel):
    customer_phone: str = "+2348031234567"
    conversation_id: Optional[UUID] = None
    items: List[CartItemInput]
    hold_minutes: int = Field(10, ge=1, le=60)


class VirtualNubanRead(CamelModel):
    bank_name: str
    bank_code: str
    account_number: str
    account_name: str
    amount_kobo: int
    amount_naira: float
    expires_in_seconds: int


class CartResponse(CamelModel):
    id: UUID
    customer_phone: str
    total_amount_kobo: int
    total_amount_naira: float
    cart_status: str
    expires_at: datetime
    virtual_nuban: Optional[VirtualNubanRead] = None


class LedgerValidationRequest(CamelModel):
    assets: float = 150000.0
    liabilities: float = 50000.0
    equity: float = 100000.0
    transaction_ref: str = "TXN_NG_9812"
    received_amount: float = 45000.0
    expected_amount: float = 45000.0


class LedgerValidationResponse(CamelModel):
    transaction_ref: str
    assets: float
    liabilities: float
    equity: float
    is_balanced: bool
    is_amount_matched: bool
    variance_naira: float
    status: Literal["SETTLED_BALANCED", "MISMATCH_ALERT"]
    ai_explanation: Optional[str] = None
    accounting_equation: str

