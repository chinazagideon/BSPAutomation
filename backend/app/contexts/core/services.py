"""Tenant infrastructure and merchant profile management services."""

from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.contexts.core.models import Merchant, User
from app.contexts.core.schemas import MerchantCreate
from app.core.security import hash_password, verify_password, create_access_token


class CoreService:
    @staticmethod
    async def create_merchant(session: AsyncSession, data: MerchantCreate) -> Merchant:
        merchant = Merchant(
            business_name=data.business_name,
            slug=data.slug,
            bsp_provider=data.bsp_provider,
            whatsapp_business_phone=data.whatsapp_business_phone,
            whatsapp_phone_number_id=data.whatsapp_phone_number_id,
            default_currency=data.default_currency,
            variance_tolerance_kobo=data.variance_tolerance_kobo,
            anti_ghosting_hold_seconds=data.anti_ghosting_hold_seconds,
        )
        session.add(merchant)
        await session.flush()
        return merchant

    @staticmethod
    async def get_merchant_by_id(session: AsyncSession, merchant_id: UUID) -> Optional[Merchant]:
        result = await session.execute(select(Merchant).where(Merchant.id == merchant_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_merchants(session: AsyncSession, limit: int = 50) -> List[Merchant]:
        result = await session.execute(select(Merchant).limit(limit))
        return list(result.scalars().all())
