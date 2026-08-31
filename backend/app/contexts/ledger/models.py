"""SQLAlchemy Models for Checkout & Ledger Bounded Context (4-Leg Double Entry)."""

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
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class CheckoutCart(Base):
    """Anti-Ghosting cart holding items while customer completes USSD / Mobile bank transfer."""
    __tablename__ = "checkout_carts"
    __table_args__ = {"schema": "ledger"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    customer_phone = Column(String(32), nullable=False)
    cart_status = Column(String(32), nullable=False, default="HELD_PENDING_TRANSFER")
    total_amount_kobo = Column(BigInteger, nullable=False)
    currency = Column(CHAR(3), nullable=False, default="NGN")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")
    virtual_nuban = relationship("VirtualNuban", back_populates="cart", uselist=False)


class CartItem(Base):
    """Individual line item in an anti-ghosting checkout cart."""
    __tablename__ = "cart_items"
    __table_args__ = {"schema": "ledger"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id = Column(UUID(as_uuid=True), ForeignKey("ledger.checkout_carts.id", ondelete="CASCADE"), nullable=False)
    item_sku = Column(String(64), nullable=False)
    item_title = Column(String(256), nullable=False)
    unit_price_kobo = Column(BigInteger, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    subtotal_kobo = Column(BigInteger, nullable=False)

    cart = relationship("CheckoutCart", back_populates="items")


class VirtualNuban(Base):
    """Dedicated temporary 10-digit virtual bank account for unambiguous settlement matching."""
    __tablename__ = "virtual_nubans"
    __table_args__ = {"schema": "ledger"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    cart_id = Column(UUID(as_uuid=True), ForeignKey("ledger.checkout_carts.id", ondelete="SET NULL"), nullable=True)
    bank_name = Column(String(128), nullable=False, default="Moniepoint MFB")
    bank_code = Column(String(16), nullable=False, default="50515")
    account_number = Column(String(10), nullable=False)
    account_name = Column(String(256), nullable=False)
    status = Column(String(32), nullable=False, default="AVAILABLE")
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    quarantine_until = Column(DateTime(timezone=True), nullable=True)

    cart = relationship("CheckoutCart", back_populates="virtual_nuban")


class LedgerAccount(Base):
    """Chart of accounts for multi-tenant double-entry ledger."""
    __tablename__ = "ledger_accounts"
    __table_args__ = {"schema": "ledger"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    account_code = Column(String(32), nullable=False)
    account_name = Column(String(128), nullable=False)
    account_type = Column(String(32), nullable=False)  # ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    current_balance_kobo = Column(BigInteger, nullable=False, default=0)


class JournalEntry(Base):
    """Immutable accounting journal header."""
    __tablename__ = "journal_entries"
    __table_args__ = {"schema": "ledger"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    cart_id = Column(UUID(as_uuid=True), ForeignKey("ledger.checkout_carts.id", ondelete="SET NULL"), nullable=True)
    transaction_reference = Column(String(128), unique=True, nullable=False)
    entry_type = Column(String(32), nullable=False, default="PAYMENT_SETTLEMENT")
    total_amount_kobo = Column(BigInteger, nullable=False)
    is_balanced = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    postings = relationship("JournalPosting", back_populates="journal_entry", cascade="all, delete-orphan")


class JournalPosting(Base):
    """Individual debit or credit posting leg enforcing Kobo precision."""
    __tablename__ = "journal_postings"
    __table_args__ = {"schema": "ledger"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("ledger.journal_entries.id", ondelete="CASCADE"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("ledger.ledger_accounts.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String(8), nullable=False)  # DEBIT, CREDIT
    amount_kobo = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    journal_entry = relationship("JournalEntry", back_populates="postings")
