"""SQLAlchemy Models for Agent Desk Bounded Context (NEPA Telemetry & 6-Field Context Card)."""

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
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Hub(Base):
    """Regional merchant support hub."""
    __tablename__ = "hubs"
    __table_args__ = {"schema": "desk"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    name = Column("name", String(128), nullable=False)
    region = Column("region", String(64), nullable=False, default="LAGOS_MAINLAND")
    is_active = Column(Boolean, nullable=False, default=True)

    @property
    def hub_name(self) -> str:
        return self.name

    @hub_name.setter
    def hub_name(self, val: str) -> None:
        self.name = val

    @property
    def region_code(self) -> str:
        return self.region

    @region_code.setter
    def region_code(self, val: str) -> None:
        self.region = val


class AgentProfile(Base):
    """Support agent profile with NEPA real-time heartbeat status."""
    __tablename__ = "agent_profiles"
    __table_args__ = {"schema": "desk"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("core.users.id", ondelete="CASCADE"), nullable=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    hub_id = Column(UUID(as_uuid=True), ForeignKey("desk.hubs.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(128), nullable=False, default="Support Agent")
    phone = Column(String(32), nullable=False, default="+2348000000000")
    work_status = Column("status", String(32), nullable=False, default="ONLINE")  # ONLINE, OFFLINE_NEPA, BUSY, ON_BREAK
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class EscalationTicket(Base):
    """Human escalation ticket injected with 6-field synthesized context card."""
    __tablename__ = "escalation_tickets"
    __table_args__ = {"schema": "desk"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("core.merchants.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("ingress.conversations.id", ondelete="CASCADE"), nullable=False)
    assigned_agent_id = Column(UUID(as_uuid=True), ForeignKey("desk.agent_profiles.id", ondelete="SET NULL"), nullable=True)
    primary_hub_id = Column(UUID(as_uuid=True), ForeignKey("desk.hubs.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(32), nullable=False, default="PENDING_ASSIGNMENT")  # PENDING_ASSIGNMENT, ASSIGNED, IN_PROGRESS, RESOLVED
    detected_budget_kobo = Column(BigInteger, nullable=False, default=0)
    urgency_tier = Column(String(16), nullable=False, default="WARM")
    dialect = Column(String(32), nullable=False, default="Standard English")
    executive_summary = Column(Text, nullable=False)
    suggested_first_response = Column(Text, nullable=False)
    key_blockers = Column(Text, nullable=False, default="None")
    pii_scrubbed = Column(Boolean, nullable=False, default=True)
    created_at = Column("escalated_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
