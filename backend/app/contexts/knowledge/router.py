"""Knowledge Base API Endpoints."""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_tenant_db, get_current_tenant, TenantContext
from app.core.response import ApiResponse
from app.contexts.knowledge.schemas import (
    KnowledgeEntryCreate,
    KnowledgeEntryResponse,
    ManifestResponse,
)
from app.contexts.knowledge.services import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base & Retrieval"])


@router.post("/entries", response_model=ApiResponse[KnowledgeEntryResponse], status_code=status.HTTP_201_CREATED)
async def create_knowledge_entry(
    request: KnowledgeEntryCreate,
    session: AsyncSession = Depends(get_tenant_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    """Creates a new knowledge entry (catalog item, policy, FAQ) for the authenticated merchant."""
    entry = await KnowledgeService.create_entry(session, tenant.merchant_id, request)
    return ApiResponse.create(data=KnowledgeEntryResponse.model_validate(entry))


@router.get("/entries", response_model=ApiResponse[List[KnowledgeEntryResponse]])
async def list_knowledge_entries(
    entry_type: Optional[str] = Query(None, description="CATALOG, POLICY, FAQ, SLANG_EXPRESSION"),
    session: AsyncSession = Depends(get_tenant_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    """Lists knowledge entries visible to the authenticated merchant (merchant + global system entries)."""
    entries = await KnowledgeService.list_entries(session, tenant.merchant_id, entry_type)
    return ApiResponse.create(data=[KnowledgeEntryResponse.model_validate(e) for e in entries])


@router.get("/manifest/{topic}", response_model=ApiResponse[ManifestResponse])
async def get_compiled_manifest(
    topic: str = "catalog",
    session: AsyncSession = Depends(get_tenant_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    """Returns the compiled Redis-cached Markdown manifest for model context injection."""
    manifest_md = await KnowledgeService.get_manifest_read_through(session, tenant.merchant_id, topic)
    resp = ManifestResponse(
        merchant_id=tenant.merchant_id,
        topic=topic,
        manifest_markdown=manifest_md,
        entry_count=len(manifest_md.splitlines()),
        is_cached=True,
    )
    return ApiResponse.create(data=resp)
