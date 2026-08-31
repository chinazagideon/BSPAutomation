"""FastAPI Router for Checkout & Ledger Endpoints."""

from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_tenant_db, get_current_tenant, TenantContext
from app.contexts.ledger.schemas import (
    CartCreateRequest,
    CartResponse,
    LedgerValidationRequest,
    LedgerValidationResponse,
)
from app.contexts.ledger.services import LedgerService

router = APIRouter(prefix="/ledger", tags=["Checkout & 4-Leg Ledger"])


@router.post("/carts", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
async def create_cart_hold(
    payload: CartCreateRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Creates an Anti-Ghosting Cart with an active 10-minute hold and
    issues a dedicated dynamic virtual NUBAN via Moniepoint MFB.
    """
    return await LedgerService.create_anti_ghosting_cart(
        session=db,
        merchant_id=UUID(tenant.merchant_id),
        request=payload,
    )


@router.post("/validate", response_model=LedgerValidationResponse)
async def validate_double_entry_ledger(payload: LedgerValidationRequest):
    """
    Validates double-entry fundamental equation (Assets = Liabilities + Equity)
    and checks for settlement payment variances.
    """
    return LedgerService.validate_ledger_equation(payload)
