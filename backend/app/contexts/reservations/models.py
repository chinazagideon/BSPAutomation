"""SQLAlchemy Models for Reservations Bounded Context (PostgreSQL GiST Range Locks)."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
    BigInteger,
    Integer,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Resource(Base):
    """Staff member, consultation room, or equipment unit."""
    __tablename__ = "resources"
    __table_args__ = {"schema": "reservations"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    resource_type = Column(String(64), nullable=False, default="STAFF")
    capacity = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)


class Service(Base):
    """Bookable appointment offering with required commitment deposit."""
    __tablename__ = "services"
    __table_args__ = {"schema": "reservations"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)
    price_kobo = Column(BigInteger, nullable=False, default=2500000)  # ₦25,000.00
    deposit_required_kobo = Column(BigInteger, nullable=False, default=500000)  # ₦5,000.00
    is_active = Column(Boolean, nullable=False, default=True)


class AtomicSlot(Base):
    """Atomic booking slot protected by PostgreSQL GiST temporal exclusion constraints."""
    __tablename__ = "atomic_slots"
    __table_args__ = {"schema": "reservations"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("reservations.resources.id", ondelete="CASCADE"), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey("reservations.services.id", ondelete="CASCADE"), nullable=False)
    customer_phone = Column(String(32), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="HELD_PENDING_PAYMENT")
    hold_expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
