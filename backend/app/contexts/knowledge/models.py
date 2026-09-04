"""Knowledge Base Models under schema 'knowledge' with Multi-Tenant RLS Support."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class KnowledgeEntry(Base):
    """
    Unified polymorphic knowledge repository table.
    Stores catalogs, FAQs, business rules, policies, and local Nigerian slang phrases.
    Nullable merchant_id:
      - NULL = Global system knowledge (e.g. system Nigerian Pidgin slang dictionary)
      - Non-null = Tenant-isolated proprietary knowledge (e.g. merchant catalog, custom pricing)
    """
    __tablename__ = "entries"
    __table_args__ = (
        Index("idx_knowledge_entries_merchant_type", "merchant_id", "entry_type"),
        Index("idx_knowledge_entries_active", "is_active"),
        {"schema": "knowledge"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.merchants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    entry_type = Column(String(32), nullable=False, default="FAQ")  # CATALOG, POLICY, FAQ, SLANG_EXPRESSION, DOC_CHUNK
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
