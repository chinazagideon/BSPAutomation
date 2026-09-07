"""Knowledge Base Pydantic Schemas."""

from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class KnowledgeEntryCreate(BaseModel):
    entry_type: str = Field("FAQ", description="CATALOG, POLICY, FAQ, SLANG_EXPRESSION, DOC_CHUNK")
    title: str
    content: str
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class KnowledgeEntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class KnowledgeEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: Optional[UUID] = None
    entry_type: str
    title: str
    content: str
    metadata_json: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ManifestResponse(BaseModel):
    merchant_id: UUID
    topic: str
    manifest_markdown: str
    entry_count: int
    is_cached: bool = True
