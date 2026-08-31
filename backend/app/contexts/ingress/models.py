"""SQLAlchemy Models for Ingress & NLU Bounded Context."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
    BigInteger,
    Integer,
    Numeric,
    DateTime,
    ForeignKey,
    JSON,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class WebhookEvent(Base):
    """Raw incoming webhook audit record acknowledging Meta/Termii under <25ms."""
    __tablename__ = "webhook_events"
    __table_args__ = {"schema": "ingress"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False, default="META_CLOUD")
    event_type = Column(String(64), nullable=False)
    raw_payload = Column(JSON, nullable=False)
    signature_verified = Column(Boolean, nullable=False, default=True)
    ack_latency_ms = Column(Integer, nullable=False, default=12)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Conversation(Base):
    """Active customer conversation tracking lead scores, funnel state, and dialect."""
    __tablename__ = "conversations"
    __table_args__ = {"schema": "ingress"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    customer_phone = Column(String(32), nullable=False)
    customer_name = Column(String(256), nullable=True)
    detected_dialect = Column(String(32), nullable=False, default="Nigerian Pidgin")
    lead_tier = Column(String(16), nullable=False, default="WARM")
    lead_score = Column(Integer, nullable=False, default=50)
    funnel_stage = Column(String(32), nullable=False, default="discovery")
    opt_out_status = Column(Boolean, nullable=False, default=False)
    assigned_agent_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """Individual incoming or outgoing WhatsApp message with PII redaction and NLU routing audit."""
    __tablename__ = "messages"
    __table_args__ = {"schema": "ingress"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("ingress.conversations.id", ondelete="CASCADE"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String(8), nullable=False)  # INBOUND, OUTBOUND
    sender_phone = Column(String(32), nullable=False)
    raw_text_redacted = Column(Text, nullable=False)
    routing_engine = Column(String(32), nullable=False)  # FAST_PATH, CUSTOM_LOCAL_MODEL, GEMINI_LLM
    confidence_score = Column(Numeric(4, 3), nullable=False, default=0.95)
    intent_classified = Column(String(64), nullable=True)
    tokens_consumed = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")


class FastPathDictionary(Base):
    """Local Nigerian Pidgin and Commercial Slang trigram dictionary for sub-millisecond intent matching."""
    __tablename__ = "fast_path_dictionary"
    __table_args__ = {"schema": "ingress"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    phrase_pattern = Column(String(256), nullable=False)
    intent = Column(String(64), nullable=False)
    suggested_response_template = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class AIWallet(Base):
    """Merchant prepaid AI token wallet tracking consumption and cost savings in Kobo."""
    __tablename__ = "ai_wallets"
    __table_args__ = {"schema": "ingress"}

    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), primary_key=True)
    balance_kobo = Column(BigInteger, nullable=False, default=500000)  # ₦5,000.00
    bundled_tokens_remaining = Column(Integer, nullable=False, default=50000)
    total_tokens_consumed = Column(Integer, nullable=False, default=0)
    total_naira_saved = Column(BigInteger, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
