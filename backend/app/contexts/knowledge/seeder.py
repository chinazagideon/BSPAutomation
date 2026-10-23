"""Idempotent Multi-Tenant Catalog Seeder Engine (ADR-0044).

Provisions demo merchants, seeds polymorphic offerings (physical & service appointments),
and pre-warms compiled Markdown manifests in Redis.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import structlog

from app.contexts.core.services import MerchantIdentificationService
from app.contexts.core.models import Merchant, MerchantChannel
from app.contexts.knowledge.models import KnowledgeEntry
from app.contexts.knowledge.services import KnowledgeService
from app.contexts.knowledge.seed_data import (
    DEMO_MERCHANTS,
    ALABA_AGRO_MERCHANT_ID,
    LEKKI_GLOW_MERCHANT_ID,
    HORIZON_TECH_MERCHANT_ID,
    ALABA_AGRO_OFFERINGS,
    LEKKI_GLOW_OFFERINGS,
    HORIZON_TECH_OFFERINGS,
)

logger = structlog.get_logger(__name__)


class CatalogSeeder:
    """Orchestrates idempotent seeding across multi-tenant database & Redis caches."""

    @classmethod
    async def ensure_merchants(cls, session: AsyncSession) -> Dict[str, Merchant]:
        """Ensures the standard multi-tenant demo merchants and 1:N channels exist in core schema."""
        result: Dict[str, Merchant] = {}
        for m_data in DEMO_MERCHANTS:
            stmt = select(Merchant).where(Merchant.id == m_data["id"])
            existing = (await session.execute(stmt)).scalar_one_or_none()

            if not existing:
                # Check by slug to avoid duplicate key violations
                stmt_slug = select(Merchant).where(Merchant.slug == m_data["slug"])
                existing_slug = (await session.execute(stmt_slug)).scalar_one_or_none()
                if existing_slug:
                    existing = existing_slug
                else:
                    merchant = Merchant(
                        id=m_data["id"],
                        business_name=m_data["business_name"],
                        slug=m_data["slug"],
                        whatsapp_business_phone=m_data["whatsapp_business_phone"],
                        whatsapp_phone_number_id=m_data.get("whatsapp_phone_number_id"),
                    )
                    session.add(merchant)
                    existing = merchant

            result[m_data["slug"]] = existing
            await session.flush()

            # Seed 1:N channels in core.merchant_channels for this merchant
            for ch_data in m_data.get("channels", []):
                ch_stmt = select(MerchantChannel).where(
                    MerchantChannel.phone_number_id == ch_data["phone_number_id"]
                )
                existing_ch = (await session.execute(ch_stmt)).scalar_one_or_none()
                if existing_ch:
                    existing_ch.merchant_id = existing.id
                    existing_ch.business_phone = ch_data["business_phone"]
                    existing_ch.provider = ch_data.get("provider", "META_CLOUD")
                    existing_ch.channel_label = ch_data.get("channel_label", "Main Office")
                    existing_ch.is_default = ch_data.get("is_default", False)
                    existing_ch.is_active = ch_data.get("is_active", True)
                else:
                    new_ch = MerchantChannel(
                        merchant_id=existing.id,
                        phone_number_id=ch_data["phone_number_id"],
                        business_phone=ch_data["business_phone"],
                        provider=ch_data.get("provider", "META_CLOUD"),
                        channel_label=ch_data.get("channel_label", "Main Office"),
                        is_default=ch_data.get("is_default", False),
                        is_active=ch_data.get("is_active", True),
                    )
                    session.add(new_ch)

        await session.flush()
        MerchantIdentificationService.invalidate_cache()
        return result

    @classmethod
    async def seed_merchant_catalog(
        cls,
        session: AsyncSession,
        merchant_id: UUID,
        items: List[Dict[str, Any]],
        reset: bool = False,
    ) -> List[KnowledgeEntry]:
        """Idempotently seeds a collection of offerings for a merchant."""
        if reset:
            # Purge existing catalog entries for clean slate
            await session.execute(
                delete(KnowledgeEntry).where(
                    KnowledgeEntry.merchant_id == merchant_id,
                    KnowledgeEntry.entry_type == "CATALOG",
                )
            )
            await session.flush()

        seeded_entries: List[KnowledgeEntry] = []

        for item in items:
            sku = item["sku"]
            metadata = {
                "sku": sku,
                "category": item["category"],
                "search_keywords": item.get("search_keywords", []),
                "price_kobo": item["price_kobo"],
                "price_naira": item.get("price_naira", item["price_kobo"] / 100.0),
                "currency": item.get("currency", "NGN"),
                "is_available": item.get("is_available", True),
                "offering_type": item.get("offering_type", "PHYSICAL_PRODUCT"),
                "unit": item.get("unit"),
                "weight": item.get("weight"),
                "stock_quantity": item.get("stock_quantity", 0),
                "duration_minutes": item.get("duration_minutes"),
                "commitment_deposit_kobo": item.get("commitment_deposit_kobo", 0),
                "resource_type": item.get("resource_type"),
                "cancellation_notice_hours": item.get("cancellation_notice_hours"),
            }

            stmt = select(KnowledgeEntry).where(
                KnowledgeEntry.merchant_id == merchant_id,
                KnowledgeEntry.entry_type == "CATALOG",
                KnowledgeEntry.metadata_json.op("->>")("sku") == sku,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()

            if existing:
                # In-place update
                existing.title = item["title"]
                existing.content = item["content"]
                existing.metadata_json = metadata
                existing.is_active = True
                seeded_entries.append(existing)
            else:
                entry = KnowledgeEntry(
                    merchant_id=merchant_id,
                    entry_type="CATALOG",
                    title=item["title"],
                    content=item["content"],
                    metadata_json=metadata,
                    is_active=True,
                )
                session.add(entry)
                seeded_entries.append(entry)

        await session.flush()
        return seeded_entries

    @classmethod
    async def warm_redis_manifests(
        cls,
        session: AsyncSession,
        merchant_ids: List[UUID],
    ) -> Dict[str, str]:
        """Pre-compiles and caches Redis Markdown manifests for high-speed model context injection."""
        manifests: Dict[str, str] = {}
        for m_id in merchant_ids:
            try:
                manifest_md = await KnowledgeService.compile_manifest(
                    session=session,
                    merchant_id=m_id,
                    topic="catalog",
                )
                manifests[str(m_id)] = manifest_md
            except Exception as err:
                logger.warning("warm_manifest_failed", merchant_id=str(m_id), error=str(err))
        return manifests

    @classmethod
    async def seed_all(
        cls,
        session: AsyncSession,
        reset: bool = False,
        merchant_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Main entry point: ensures merchants, seeds catalogs, and warms Redis manifests."""
        merchants_map = await cls.ensure_merchants(session)

        catalog_mapping = {
            "alaba-agro": (ALABA_AGRO_MERCHANT_ID, ALABA_AGRO_OFFERINGS),
            "lekki-glow": (LEKKI_GLOW_MERCHANT_ID, LEKKI_GLOW_OFFERINGS),
            "horizon-tech": (HORIZON_TECH_MERCHANT_ID, HORIZON_TECH_OFFERINGS),
        }

        total_seeded = 0
        warmed_merchants: List[UUID] = []

        for slug, (m_id, items) in catalog_mapping.items():
            if merchant_slug and merchant_slug != slug:
                continue

            actual_merchant = merchants_map.get(slug)
            target_id = actual_merchant.id if actual_merchant else m_id

            entries = await cls.seed_merchant_catalog(
                session=session,
                merchant_id=target_id,
                items=items,
                reset=reset,
            )
            total_seeded += len(entries)
            warmed_merchants.append(target_id)

        # Pre-warm Redis manifests
        manifests = await cls.warm_redis_manifests(session, warmed_merchants)

        await session.commit()

        logger.info(
            "catalog_seeding_completed",
            merchants_count=len(warmed_merchants),
            offerings_seeded=total_seeded,
            reset_mode=reset,
        )

        return {
            "status": "COMPLETED",
            "merchants_seeded": len(warmed_merchants),
            "offerings_seeded": total_seeded,
            "manifests_warmed": len(manifests),
            "reset": reset,
        }
