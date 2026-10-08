import re
import difflib
import structlog
from uuid import UUID
from typing import List, Optional, Dict, Any, Union, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, desc
from redis.asyncio import Redis

from app.core.config import settings
from app.contexts.knowledge.models import KnowledgeEntry
from app.contexts.knowledge.schemas import KnowledgeEntryCreate, KnowledgeEntryUpdate
from app.contexts.knowledge.offering_schemas import CoreOfferingDTO, OfferingType
from app.core.redis import get_redis_client

logger = structlog.get_logger(__name__)

DEFAULT_DEMO_OFFERINGS: List[Dict[str, Any]] = [
    {
        "sku": "RICE_MAMA_GOLD_50KG",
        "title": "Mama Gold Rice 50kg",
        "content": "Premium Nigerian parboiled rice, 50kg bag. Stone free, sweet aroma.",
        "category": "rice",
        "search_keywords": ["mama gold", "rice", "50kg", "parboiled", "bag"],
        "price_kobo": 7800000,
        "price_naira": 78000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": "PHYSICAL_PRODUCT",
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 25,
    },
    {
        "sku": "RICE_ROYAL_STALLION_50KG",
        "title": "Royal Stallion Rice 50kg",
        "content": "Imported high quality fragrant rice, 50kg bag.",
        "category": "rice",
        "search_keywords": ["royal stallion", "stallion", "rice", "50kg", "bag"],
        "price_kobo": 8000000,
        "price_naira": 80000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": "PHYSICAL_PRODUCT",
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 15,
    },
    {
        "sku": "SUGAR_DANGOTE_50KG",
        "title": "Dangote Sugar 50kg",
        "content": "Refined pure white granulated sugar from Dangote, 50kg bag.",
        "category": "sugar",
        "search_keywords": ["dangote", "sugar", "50kg", "granulated", "bag"],
        "price_kobo": 8400000,
        "price_naira": 84000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": "PHYSICAL_PRODUCT",
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 45,
    },
    {
        "sku": "SUGAR_BUA_50KG",
        "title": "BUA Sugar 50kg",
        "content": "Fortified white granulated sugar from BUA, 50kg commercial bag.",
        "category": "sugar",
        "search_keywords": ["bua", "sugar", "50kg", "bag"],
        "price_kobo": 8200000,
        "price_naira": 82000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": "PHYSICAL_PRODUCT",
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 30,
    },
    {
        "sku": "SUGAR_ST_LOUIS_500G",
        "title": "St. Louis Sugar Cube (500g Pack)",
        "content": "Classic French cube sugar, 500g retail pack.",
        "category": "sugar",
        "search_keywords": ["st louis", "st. louis", "sugar", "cube", "500g", "pack"],
        "price_kobo": 180000,
        "price_naira": 1800.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": "PHYSICAL_PRODUCT",
        "unit": "pack",
        "weight": "500g",
        "stock_quantity": 120,
    },
]


def _compute_trigram_similarity(s1: str, s2: str) -> float:
    s1 = f"  {s1.lower().strip()} "
    s2 = f"  {s2.lower().strip()} "
    t1 = set(s1[i : i + 3] for i in range(len(s1) - 2))
    t2 = set(s2[i : i + 3] for i in range(len(s2) - 2))
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def _entry_to_dto(entry: KnowledgeEntry) -> CoreOfferingDTO:
    meta = entry.metadata_json or {}
    price_kobo = meta.get("price_kobo")
    if price_kobo is None:
        price_naira = meta.get("price_naira", 0.0)
        price_kobo = int(price_naira * 100)
    else:
        price_naira = meta.get("price_naira", price_kobo / 100.0)

    offering_type_str = meta.get("offering_type", OfferingType.PHYSICAL_PRODUCT.value)
    try:
        offering_type = OfferingType(offering_type_str)
    except Exception:
        offering_type = OfferingType.PHYSICAL_PRODUCT

    is_available = meta.get("is_available", meta.get("in_stock", True))
    stock_qty = meta.get("stock_quantity")
    if stock_qty is not None and stock_qty <= 0 and offering_type == OfferingType.PHYSICAL_PRODUCT:
        is_available = False

    return CoreOfferingDTO(
        id=str(entry.id) if entry.id else None,
        merchant_id=str(entry.merchant_id) if entry.merchant_id else None,
        sku=meta.get("sku", str(entry.id)),
        title=entry.title,
        description=entry.content,
        offering_type=offering_type,
        price_kobo=price_kobo,
        price_naira=float(price_naira),
        currency=meta.get("currency", "NGN"),
        is_available=is_available,
        category=meta.get("category", "general"),
        search_keywords=meta.get("search_keywords", []),
        metadata=meta,
    )


def _dict_to_dto(d: Dict[str, Any], merchant_id: Optional[str] = None) -> CoreOfferingDTO:
    price_kobo = d.get("price_kobo", int(d.get("price_naira", 0.0) * 100))
    price_naira = d.get("price_naira", price_kobo / 100.0)
    category = d.get("category", "general")
    sku = d.get("sku", "")
    title = d.get("title", d.get("name", sku))
    keywords = d.get("search_keywords", [category, title.lower(), sku.lower()])
    is_available = d.get("is_available", d.get("in_stock", True))
    if d.get("stock_quantity", 1) <= 0:
        is_available = False

    return CoreOfferingDTO(
        id=f"demo-{sku}",
        merchant_id=merchant_id,
        sku=sku,
        title=title,
        description=d.get("content", d.get("description", f"{title} - ₦{price_naira:,.2f}")),
        offering_type=OfferingType.PHYSICAL_PRODUCT,
        price_kobo=price_kobo,
        price_naira=float(price_naira),
        currency=d.get("currency", "NGN"),
        is_available=is_available,
        category=category,
        search_keywords=keywords,
        metadata=d,
    )


def _score_offering(offering: CoreOfferingDTO, query: str) -> Tuple[int, int, float]:
    """Returns (in_stock_rank, tier_priority, similarity_score).

    tier_priority:
      3: Tier 1 - Exact category match
      2: Tier 2 - Keyword match in search_keywords
      1: Tier 3 - Trigram / fuzzy similarity on title/content
      0: No match
    """
    q = query.lower().strip()
    in_stock = 1 if offering.is_available else 0

    if not q or q in ["all", "catalog", "products", "offerings"]:
        return (in_stock, 1, 1.0)

    q_tokens = [t for t in re.findall(r"\w+", q) if len(t) > 1]
    tier = 0
    sim_score = 0.0

    # Tier 1: Exact category match
    cat = offering.category.lower().strip()
    if cat == q or cat in q_tokens or any(tok in cat for tok in q_tokens):
        tier = 3
        sim_score = 1.0

    # Tier 2: Keyword match in search_keywords
    keywords = [k.lower().strip() for k in offering.search_keywords]
    for kw in keywords:
        if kw == q or kw in q or any(tok == kw or kw in tok for tok in q_tokens):
            tier = max(tier, 2)
            sim_score = max(sim_score, 0.9)
            break

    # Tier 3: Trigram similarity & fuzzy match on title and description/content
    title = offering.title.lower()
    desc = offering.description.lower()

    if q in title or any(tok in title for tok in q_tokens):
        tier = max(tier, 1)
        sim_score = max(sim_score, 0.8)

    tri_sim = max(_compute_trigram_similarity(q, title), _compute_trigram_similarity(q, desc))
    seq_sim = difflib.SequenceMatcher(None, q, title).ratio()

    title_words = [w for w in re.findall(r"\w+", title) if len(w) > 1]
    word_sim = 0.0
    for q_tok in q_tokens:
        for t_word in title_words:
            w_ratio = difflib.SequenceMatcher(None, q_tok, t_word).ratio()
            word_sim = max(word_sim, w_ratio)

    max_fuzzy = max(tri_sim, seq_sim, word_sim)
    if max_fuzzy >= 0.70 or tri_sim >= 0.25:
        tier = max(tier, 1)
        sim_score = max(sim_score, max_fuzzy)

    return (in_stock, tier, sim_score)


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

    @classmethod
    async def seed_demo_offerings(
        cls,
        session: AsyncSession,
        merchant_id: Union[UUID, str],
    ) -> List[KnowledgeEntry]:
        """Seeds standard demo catalog entries for the given merchant into knowledge.entries."""
        merchant_uuid = UUID(str(merchant_id)) if merchant_id else None
        seeded_entries: List[KnowledgeEntry] = []
        for item in DEFAULT_DEMO_OFFERINGS:
            stmt = select(KnowledgeEntry).where(
                KnowledgeEntry.merchant_id == merchant_uuid,
                KnowledgeEntry.entry_type == "CATALOG",
                KnowledgeEntry.metadata_json.op("->>")("sku") == item["sku"],
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                seeded_entries.append(existing)
                continue

            entry = KnowledgeEntry(
                merchant_id=merchant_uuid,
                entry_type="CATALOG",
                title=item["title"],
                content=item["content"],
                metadata_json={
                    "sku": item["sku"],
                    "category": item["category"],
                    "search_keywords": item["search_keywords"],
                    "price_kobo": item["price_kobo"],
                    "price_naira": item["price_naira"],
                    "currency": item["currency"],
                    "is_available": item["is_available"],
                    "offering_type": item["offering_type"],
                    "unit": item.get("unit", "unit"),
                    "weight": item.get("weight"),
                    "stock_quantity": item.get("stock_quantity", 50 if item.get("is_available", True) else 0),
                },
                is_active=True,
            )
            session.add(entry)
            seeded_entries.append(entry)
        await session.flush()
        return seeded_entries

    @classmethod
    async def get_offering_by_sku(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[CoreOfferingDTO]:
        """Retrieves a single offering by SKU with DB search and test/dev mock fallback."""
        session: Optional[AsyncSession] = None
        merchant_id: Optional[Union[UUID, str]] = None
        sku: str = ""

        if len(args) == 3 and isinstance(args[0], AsyncSession):
            session, merchant_id, sku = args[0], args[1], args[2]
        elif len(args) == 2:
            if isinstance(args[0], AsyncSession):
                session, sku = args[0], args[1]
                merchant_id = kwargs.get("merchant_id")
            else:
                merchant_id, sku = args[0], args[1]
                session = kwargs.get("session")
        elif len(args) == 1:
            sku = args[0]
            merchant_id = kwargs.get("merchant_id")
            session = kwargs.get("session")
        else:
            sku = kwargs.get("sku", "")
            merchant_id = kwargs.get("merchant_id")
            session = kwargs.get("session")

        sku = sku.strip()
        merchant_uuid = UUID(str(merchant_id)) if merchant_id else None

        # 1. Search in DB
        async def _query_db(sess: AsyncSession) -> Optional[CoreOfferingDTO]:
            conditions = [
                KnowledgeEntry.entry_type == "CATALOG",
                KnowledgeEntry.is_active.is_(True),
                KnowledgeEntry.metadata_json.op("->>")("sku") == sku,
            ]
            if merchant_uuid:
                conditions.append(or_(KnowledgeEntry.merchant_id == merchant_uuid, KnowledgeEntry.merchant_id.is_(None)))
            stmt = select(KnowledgeEntry).where(*conditions)
            res = await sess.execute(stmt)
            entry = res.scalars().first()
            if entry:
                return _entry_to_dto(entry)
            return None

        if session:
            found = await _query_db(session)
            if found:
                return found
        else:
            try:
                from app.core.database import async_session_factory
                async with async_session_factory() as sess:
                    found = await _query_db(sess)
                    if found:
                        return found
            except Exception as err:
                logger.warning("db_get_offering_by_sku_failed", error=str(err))

        # 2. Environment safety gate on fallback
        env = getattr(settings, "ENVIRONMENT", "development").lower()
        if env not in ["production"]:
            for item in DEFAULT_DEMO_OFFERINGS:
                if item["sku"].lower() == sku.lower():
                    return _dict_to_dto(item, str(merchant_id) if merchant_id else None)

        return None

    @classmethod
    async def search_catalog_offerings(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> List[CoreOfferingDTO]:
        """Tiered Discovery Catalog Search under Multi-Tenant RLS with Environment Fallback Gate."""
        session: Optional[AsyncSession] = None
        merchant_id: Optional[Union[UUID, str]] = None
        query: str = ""
        limit: int = kwargs.get("limit", 10)

        if len(args) >= 3 and isinstance(args[0], AsyncSession):
            session, merchant_id, query = args[0], args[1], args[2]
            if len(args) >= 4:
                limit = args[3]
        elif len(args) >= 2:
            merchant_id, query = args[0], args[1]
            session = kwargs.get("session")
            if len(args) >= 3:
                limit = args[2]
        elif len(args) == 1:
            query = args[0]
            merchant_id = kwargs.get("merchant_id")
            session = kwargs.get("session")
        else:
            merchant_id = kwargs.get("merchant_id")
            query = kwargs.get("query", "")
            session = kwargs.get("session")

        merchant_uuid = UUID(str(merchant_id)) if merchant_id else None

        # 1. Fetch catalog entries from PostgreSQL
        db_entries: List[KnowledgeEntry] = []
        async def _fetch_from_db(sess: AsyncSession) -> List[KnowledgeEntry]:
            conditions = [
                KnowledgeEntry.entry_type == "CATALOG",
                KnowledgeEntry.is_active.is_(True),
            ]
            if merchant_uuid:
                conditions.append(or_(KnowledgeEntry.merchant_id == merchant_uuid, KnowledgeEntry.merchant_id.is_(None)))
            stmt = select(KnowledgeEntry).where(*conditions)
            res = await sess.execute(stmt)
            return list(res.scalars().all())

        if session:
            try:
                db_entries = await _fetch_from_db(session)
            except Exception as err:
                logger.warning("db_catalog_search_failed", error=str(err))
        else:
            try:
                from app.core.database import async_session_factory
                async with async_session_factory() as sess:
                    db_entries = await _fetch_from_db(sess)
            except Exception as err:
                logger.warning("db_catalog_search_session_failed", error=str(err))

        # 2. Check candidates & Environment Safety Gate
        candidates: List[CoreOfferingDTO] = []
        if db_entries:
            candidates = [_entry_to_dto(e) for e in db_entries]
        else:
            env = getattr(settings, "ENVIRONMENT", "development").lower()
            if env == "production":
                # In production, strict adherence: return empty list on 0 DB rows
                return []
            else:
                # In development and test, fall back to demo commodity catalog
                candidates = [_dict_to_dto(d, str(merchant_id) if merchant_id else None) for d in DEFAULT_DEMO_OFFERINGS]

        # 3. Score and prioritize candidates using 3-Tier engine + in-stock priority
        scored: List[Tuple[CoreOfferingDTO, Tuple[int, int, float]]] = []
        for cand in candidates:
            score_tuple = _score_offering(cand, query)
            in_stock, tier, sim = score_tuple
            if tier > 0:
                scored.append((cand, score_tuple))

        # Sort by (in_stock, tier, sim) descending
        scored.sort(key=lambda x: (x[1][0], x[1][1], x[1][2]), reverse=True)

        return [item[0] for item in scored[:limit]]
