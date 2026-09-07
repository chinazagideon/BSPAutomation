"""Knowledge Base Context Provider for Context Aggregator (ADR-0041)."""

from typing import Dict, Any, Optional
from uuid import UUID

from app.core.generation.context import ContextProvider, ContextSlice
from app.core.database import async_session_factory, tenant_session_scope
from app.contexts.knowledge.services import KnowledgeService


class KnowledgeSliceProvider(ContextProvider):
    """Resolves merchant product catalogs, FAQs, and business policies for context aggregation."""

    @property
    def slice_name(self) -> str:
        return "knowledge"

    async def resolve(
        self,
        merchant_id: Optional[UUID],
        customer_phone: Optional[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> ContextSlice:
        if not merchant_id:
            return ContextSlice(
                slice_name=self.slice_name,
                content="Standard Merchant Operational Policies Apply.",
                token_estimate=10,
            )

        opts = options or {}
        topic = opts.get("topic", "catalog")

        async with tenant_session_scope(merchant_id) as session:
            manifest_md = await KnowledgeService.get_manifest_read_through(
                session=session,
                merchant_id=merchant_id,
                topic=topic,
            )

        token_est = max(10, len(manifest_md.split()) * 2)
        return ContextSlice(
            slice_name=self.slice_name,
            content=manifest_md,
            token_estimate=token_est,
            is_cached=True,
        )
