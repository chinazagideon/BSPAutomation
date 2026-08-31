"""FastAPI Router for Tenant Core Infrastructure and Authentication."""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.tenant import get_current_tenant, TenantContext
from app.contexts.core.schemas import MerchantCreate, MerchantRead
from app.contexts.core.services import CoreService

router = APIRouter(prefix="/core", tags=["Core Tenant Infrastructure"])


@router.post("/merchants", response_model=MerchantRead, status_code=status.HTTP_201_CREATED)
async def create_merchant(
    payload: MerchantCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Registers a new Nigerian SME tenant on the platform."""
    return await CoreService.create_merchant(db, payload)


@router.get("/merchants", response_model=List[MerchantRead])
async def list_merchants(
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
):
    """Lists registered merchant profiles (Admin API)."""
    return await CoreService.list_merchants(db, limit)


@router.get("/merchants/me", response_model=MerchantRead)
async def get_current_merchant_profile(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns the profile of the authenticated active tenant."""
    merchant = await CoreService.get_merchant_by_id(db, UUID(tenant.merchant_id))
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant
