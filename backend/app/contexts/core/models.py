"""SQLAlchemy Models for the Core Tenant Infrastructure."""

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
    CHAR,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Merchant(Base):
    """Tenant profile and business configuration."""
    __tablename__ = "merchants"
    __table_args__ = {"schema": "core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_name = Column(String(256), nullable=False)
    slug = Column(String(128), unique=True, nullable=False)
    bsp_provider = Column(String(32), nullable=False, default="META_CLOUD")
    whatsapp_business_phone = Column(String(32), nullable=False)
    whatsapp_phone_number_id = Column(String(64), nullable=True)
    default_currency = Column(CHAR(3), nullable=False, default="NGN")
    variance_tolerance_kobo = Column(BigInteger, nullable=False, default=0)
    anti_ghosting_hold_seconds = Column(Integer, nullable=False, default=600)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    users = relationship("User", back_populates="merchant", cascade="all, delete-orphan")
    channels = relationship("MerchantChannel", back_populates="merchant", cascade="all, delete-orphan")


class MerchantChannel(Base):
    """1:N WhatsApp phone number channels belonging to a merchant."""
    __tablename__ = "merchant_channels"
    __table_args__ = {"schema": "core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_number_id = Column(String(64), unique=True, nullable=False, index=True)
    business_phone = Column(String(32), nullable=False)
    provider = Column(String(32), nullable=False, default="META_CLOUD")
    channel_label = Column(String(64), nullable=False, default="Main Office")
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    merchant = relationship("Merchant", back_populates="channels")


class User(Base):
    """User account within a merchant tenant."""
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(256), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    full_name = Column(String(256), nullable=False)
    role = Column(String(32), nullable=False, default="AGENT")
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    merchant = relationship("Merchant", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    """Cryptographically hashed rotating refresh token with family lineage tracking."""
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    family_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    is_revoked = Column(Boolean, nullable=False, default=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="refresh_tokens")
    merchant = relationship("Merchant")


class AIWallet(Base):
    """Merchant prepaid AI token wallet tracking consumption and cost savings in Kobo (ADR-0039)."""
    __tablename__ = "ai_wallets"
    __table_args__ = {"schema": "core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), unique=True, nullable=False)
    balance_kobo = Column(BigInteger, nullable=False, default=0)
    monthly_hard_cap_kobo = Column(BigInteger, nullable=False, default=1000000)
    bundled_tokens_remaining = Column(Integer, nullable=False, default=10000)
    total_tokens_consumed = Column(BigInteger, nullable=False, default=0)
    total_kobo_spent = Column(BigInteger, nullable=False, default=0)
    estimated_kobo_saved = Column(BigInteger, nullable=False, default=0)
    is_locked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AITokenLedgerEntry(Base):
    """Immutable ledger entry tracking token consumption with source context attribution (ADR-0039 & ADR-0040)."""
    __tablename__ = "ai_token_ledger"
    __table_args__ = {"schema": "core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    source_context = Column(String(32), nullable=False, default="INGRESS")  # INGRESS, DESK, RESERVATIONS, CHECKOUT
    task_priority = Column(String(32), nullable=False, default="CUSTOMER_FACING")
    tokens_consumed = Column(Integer, nullable=False)
    kobo_cost = Column(BigInteger, nullable=False, default=0)
    model_name = Column(String(64), nullable=False, default="gemini-3.7-flash")
    reference_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

