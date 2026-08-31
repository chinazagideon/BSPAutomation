"""Application Services for Atomic Slot Reservation and Concurrency Lock Management."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException

from app.contexts.reservations.models import AtomicSlot, Service
from app.contexts.reservations.schemas import SlotHoldRequest, SlotHoldResponse


class ReservationService:
    @staticmethod
    async def create_provisional_hold(
        session: AsyncSession,
        merchant_id: UUID,
        request: SlotHoldRequest,
    ) -> SlotHoldResponse:
        """
        Places a 10-minute anti-no-show provisional reservation hold on an atomic slot,
        checking for active overlapping bookings on the target resource.
        """
        # Concurrency overlap check
        overlap_query = await session.execute(
            select(AtomicSlot).where(
                and_(
                    AtomicSlot.merchant_id == merchant_id,
                    AtomicSlot.resource_id == request.resource_id,
                    AtomicSlot.status.in_(["HELD_PENDING_PAYMENT", "CONFIRMED"]),
                    AtomicSlot.start_time < request.end_time,
                    AtomicSlot.end_time > request.start_time,
                )
            )
        )
        existing = overlap_query.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Conflict: Selected appointment slot is already reserved or held by another customer.",
            )

        # Retrieve service pricing
        svc_query = await session.execute(select(Service).where(Service.id == request.service_id))
        service = svc_query.scalar_one_or_none()
        deposit_kobo = service.deposit_required_kobo if service else 500000

        hold_expires_at = datetime.now(timezone.utc) + timedelta(minutes=request.hold_minutes)

        slot = AtomicSlot(
            merchant_id=merchant_id,
            resource_id=request.resource_id,
            service_id=request.service_id,
            customer_phone=request.customer_phone,
            start_time=request.start_time,
            end_time=request.end_time,
            status="HELD_PENDING_PAYMENT",
            hold_expires_at=hold_expires_at,
        )
        session.add(slot)
        await session.flush()

        return SlotHoldResponse(
            slot_id=slot.id,
            status=slot.status,
            resource_id=slot.resource_id,
            service_id=slot.service_id,
            customer_phone=slot.customer_phone,
            start_time=slot.start_time,
            end_time=slot.end_time,
            hold_expires_at=slot.hold_expires_at,
            deposit_required_naira=deposit_kobo / 100.0,
            deposit_required_kobo=deposit_kobo,
        )
