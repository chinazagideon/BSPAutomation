"""FastAPI Router for Atomic Slot Reservations."""

from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_tenant_db, get_current_tenant, TenantContext
from app.core.response import ApiResponse
from app.contexts.reservations.schemas import SlotHoldRequest, SlotHoldResponse
from app.contexts.reservations.services import ReservationService

router = APIRouter(prefix="/reservations", tags=["Atomic Slot Reservations"])


@router.post("/holds", response_model=ApiResponse[SlotHoldResponse], status_code=status.HTTP_201_CREATED)
async def create_slot_hold(
    payload: SlotHoldRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Places an atomic 10-minute anti-no-show hold on an appointment slot with GiST range exclusion.
    """
    result = await ReservationService.create_provisional_hold(
        session=db,
        merchant_id=UUID(tenant.merchant_id),
        request=payload,
    )
    return ApiResponse.create(data=result)

