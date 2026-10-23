"""SQLAlchemy Models for Ingress & NLU Bounded Context."""

import uuid
from typing import Optional, Any
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
    external_event_id = Column(String(128), nullable=True)
    raw_payload = Column(JSON, nullable=False)
    signature_verified = Column(Boolean, nullable=False, default=True)
    ack_latency_ms = Column(Integer, nullable=False, default=12)
    worker_status = Column(String(32), nullable=False, default="COMPLETED")
    worker_latency_ms = Column(Integer, nullable=False, default=0)
    received_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def created_at(self) -> datetime:
        return self.received_at

    @property
    def processed_at(self) -> Optional[datetime]:
        return self.received_at

    @processed_at.setter
    def processed_at(self, val: Any) -> None:
        self.worker_status = "COMPLETED"


class Conversation(Base):
    """Active customer conversation tracking lead scores, funnel state, and dialect."""
    __tablename__ = "conversations"
    __table_args__ = {"schema": "ingress"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("core.merchant_channels.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_phone = Column(String(32), nullable=False)
    customer_name = Column(String(128), nullable=True)
    funnel_stage = Column(String(32), nullable=False, default="discovery")
    lead_tier = Column(String(16), nullable=False, default="WARM")
    urgency_score = Column(Integer, nullable=False, default=5)
    tech_complexity = Column(Integer, nullable=False, default=3)
    detected_budget_kobo = Column(BigInteger, nullable=False, default=0)
    detected_dialect = Column(String(32), nullable=False, default="Standard English")
    extracted_entities = Column(JSON, nullable=False, default=dict)
    is_open = Column(Boolean, nullable=False, default=True)
    last_message_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    channel = relationship("MerchantChannel")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    @property
    def lead_score(self) -> int:
        return self.urgency_score * 10

    @lead_score.setter
    def lead_score(self, val: int) -> None:
        self.urgency_score = max(1, min(10, val // 10))


class Message(Base):
    """Individual incoming or outgoing WhatsApp message with PII redaction and NLU routing audit."""
    __tablename__ = "messages"
    __table_args__ = {"schema": "ingress"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("ingress.conversations.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(16), nullable=False, default="user")  # user, bot, agent, system
    raw_text = Column(Text, nullable=False)
    sanitized_text = Column(Text, nullable=False)
    intent = Column(String(64), nullable=True)
    is_fast_path = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Integer, nullable=False, default=0)
    interactive_type = Column(String(32), nullable=True)
    interactive_payload = Column(JSON, nullable=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")

    @property
    def direction(self) -> str:
        return "INBOUND" if self.sender == "user" else "OUTBOUND"

    @direction.setter
    def direction(self, val: str) -> None:
        self.sender = "user" if val == "INBOUND" else "bot"

    @property
    def raw_text_redacted(self) -> str:
        return self.sanitized_text

    @raw_text_redacted.setter
    def raw_text_redacted(self, val: str) -> None:
        self.sanitized_text = val
        if not self.raw_text:
            self.raw_text = val

    @property
    def tokens_consumed(self) -> int:
        return self.tokens_used

    @tokens_consumed.setter
    def tokens_consumed(self, val: int) -> None:
        self.tokens_used = val


class FastPathDictionary(Base):
    """Local Nigerian Pidgin and Commercial Slang trigram dictionary for sub-millisecond intent matching."""
    __tablename__ = "slang_dictionary"
    __table_args__ = {"schema": "ingress"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=True)
    phrase_pattern = Column(Text, nullable=False)
    intent = Column("intent_classification", String(64), nullable=False)
    suggested_response_template = Column("standard_english_translation", Text, nullable=False)
    category = Column(String(32), nullable=False, default="COMMERCE")
    dialect = Column(String(32), nullable=False, default="Nigerian Pidgin")
    confidence_score = Column(Numeric(4, 2), nullable=False, default=0.95)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# AIWallet is centralized under core schema per ADR-0039 & ADR-0040
from app.contexts.core.models import AIWallet

