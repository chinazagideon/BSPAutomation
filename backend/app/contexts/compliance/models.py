"""SQLAlchemy Models for Compliance & Privacy Bounded Context (NDPA 2023 & Egress Audit Trails)."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Float,
    Integer,
    DateTime,
    ForeignKey,
    CHAR,
    JSON,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ConsentEvent(Base):
    """Event-sourced, SHA-256 cryptographically chained NDPA 2023 consent audit trail."""
    __tablename__ = "consent_events"
    __table_args__ = {"schema": "compliance"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    customer_phone = Column(String(32), nullable=False)
    action = Column(String(32), nullable=False)  # OPT_IN, OPT_OUT_STOP, OPT_OUT_COMOT, EXPLICIT_REVOCATION
    channel = Column(String(32), nullable=False, default="WHATSAPP")
    previous_event_hash = Column(CHAR(64), nullable=True)
    immutable_hash = Column(CHAR(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class PiiRedactionAudit(Base):
    """Audit log of intercepted Nigerian identifiers (BVN, NIN, NUBAN, Card PAN)."""
    __tablename__ = "pii_redaction_audits"
    __table_args__ = {"schema": "compliance"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(UUID(as_uuid=True), nullable=True)
    entity_type = Column(String(32), nullable=False)  # BVN, NIN, NUBAN, CARD_PAN
    redaction_token = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class EphemeralPiiToken(Base):
    """AES-256 encrypted datastore with 24-hour retention window for token resolution."""
    __tablename__ = "ephemeral_pii_tokens"
    __table_args__ = {"schema": "compliance"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    token_key = Column(String(64), unique=True, nullable=False)
    encrypted_value = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class EgressAuditLog(Base):
    """Immutable audit record for every outbound third-party API wire transmission."""
    __tablename__ = "egress_audit_logs"
    __table_args__ = {"schema": "compliance"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    trace_id = Column(String(64), nullable=False)
    target_service = Column(String(64), nullable=False)
    http_method = Column(String(16), nullable=False)
    endpoint_url = Column(String(512), nullable=False)
    masked_headers = Column(JSON, nullable=False)
    request_body_redacted = Column(Text, nullable=True)
    request_sha256 = Column(CHAR(64), nullable=False)
    response_status_code = Column(Integer, nullable=False)
    response_body_redacted = Column(Text, nullable=True)
    response_sha256 = Column(CHAR(64), nullable=False)
    latency_ms = Column(Float, nullable=False)
    is_success = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
