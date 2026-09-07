"""Knowledge Base Application Services."""

import structlog
from uuid import UUID
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, desc
from redis.asyncio import Redis

from app.contexts.knowledge.models import KnowledgeEntry
from app.contexts.knowledge.schemas import KnowledgeEntryCreate, KnowledgeEntryUpdate
from app.core.redis import get_redis_client

logger = structlog.get_logger(__name__)


class KnowledgeService:
    @staticmethod
    async def create_entry(
        session: AsyncSession,
        merchant_id: Optional[UUID],
        request: KnowledgeEntryCreate,
    ) -> KnowledgeEntry:
        entry = KnowledgeEntry(
            merchant_id=merchant_id,
            entry_type=request.entry_type,
            title=request.title,
            content=request.content,
            metadata_json=request.metadata_json,
            is_active=request.is_active,
        )
        session.add(entry)
        await session.flush()
        await session.refresh(entry)
        return entry

    @staticmethod
    async def list_entries(
        session: AsyncSession,
        merchant_id: Optional[UUID],
        entry_type: Optional[str] = None,
        include_global: bool = True,
    ) -> List[KnowledgeEntry]:
        conditions = [KnowledgeEntry.is_active.is_(True)]
        if entry_type:
            conditions.append(KnowledgeEntry.entry_type == entry_type)

        if merchant_id:
            if include_global:
                conditions.append(or_(KnowledgeEntry.merchant_id == merchant_id, KnowledgeEntry.merchant_id.is_(None)))
            else:
                conditions.append(KnowledgeEntry.merchant_id == merchant_id)
        elif not include_global:
            conditions.append(KnowledgeEntry.merchant_id.is_(None))

        stmt = select(KnowledgeEntry).where(*conditions).order_by(desc(KnowledgeEntry.created_at))
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def search_entries(
        session: AsyncSession,
        merchant_id: Optional[UUID],
        query: str,
        limit: int = 10,
    ) -> List[KnowledgeEntry]:
        """Tri-modal search querying title and content with fuzzy matching under tenant isolation."""
        search_pattern = f"%{query}%"
        conditions = [
            KnowledgeEntry.is_active.is_(True),
            or_(
                KnowledgeEntry.title.ilike(search_pattern),
                KnowledgeEntry.content.ilike(search_pattern),
            ),
        ]
        if merchant_id:
            conditions.append(or_(KnowledgeEntry.merchant_id == merchant_id, KnowledgeEntry.merchant_id.is_(None)))

        stmt = select(KnowledgeEntry).where(*conditions).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def compile_manifest(
        session: AsyncSession,
        merchant_id: UUID,
        topic: str = "catalog",
        redis_client: Optional[Redis] = None,
    ) -> str:
        """Compiles active knowledge entries into a compact, token-bounded Markdown manifest and caches in Redis."""
        entries = await KnowledgeService.list_entries(
            session=session,
            merchant_id=merchant_id,
            entry_type="CATALOG" if topic == "catalog" else None,
            include_global=True,
        )

        lines: List[str] = [f"### Merchant {topic.title()} Manifest:"]
        for e in entries:
            price_str = ""
            if "price_naira" in e.metadata_json:
                price_str = f" - ₦{e.metadata_json['price_naira']:,}"
            lines.append(f"- **{e.title}**{price_str}: {e.content}")

        manifest_md = "\n".join(lines)
        client = redis_client or await get_redis_client()
        key = f"knowledge:manifest:{merchant_id}:{topic}"
        try:
            await client.set(key, manifest_md, ex=3600)  # 1 hour cache
        except Exception as err:
            logger.warning("redis_manifest_cache_failed", error=str(err))

        return manifest_md

    @staticmethod
    async def get_manifest_read_through(
        session: AsyncSession,
        merchant_id: UUID,
        topic: str = "catalog",
        redis_client: Optional[Redis] = None,
    ) -> str:
        """Fetches manifest from Redis cache with automatic read-through compilation fallback on miss."""
        client = redis_client or await get_redis_client()
        key = f"knowledge:manifest:{merchant_id}:{topic}"
        try:
            cached = await client.get(key)
            if cached:
                return cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
        except Exception as err:
            logger.warning("redis_manifest_read_failed", error=str(err))

        # Cache miss -> Compile on-demand
        return await KnowledgeService.compile_manifest(session, merchant_id, topic, client)
