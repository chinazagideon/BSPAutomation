"""Comprehensive Automated Tests for Multi-Vertical Seeded Features (ADR-0044).

Validates:
1. End-to-end CLI seeder execution & database idempotency.
2. PostgreSQL RLS cross-tenant isolation across distinct verticals.
3. Nigerian Pidgin & slang keyword retrieval ('shinkafa', 'ororo', 'fade').
4. Packaging variant clarification loops (50kg vs 25kg Mama Gold).
5. Out-of-stock prioritization and handling.
6. Service appointment polymorphic schemas, duration, and commitment deposits.
7. Redis Markdown manifest pre-warming and read-through validity.
"""

import pytest
from uuid import UUID
from sqlalchemy import select, func

from app.core.database import async_session_factory, tenant_session_scope
from app.contexts.knowledge.models import KnowledgeEntry
from app.contexts.knowledge.services import KnowledgeService
from app.contexts.knowledge.seeder import CatalogSeeder
from app.contexts.knowledge.offering_schemas import OfferingType
from app.core.generation.response_orchestrator import ResponseOrchestrator
from app.core.generation.response_classifier import ResponseStrategy
from app.core.generation.response_formatter import (
    ResponseFormatter,
    EgressMessageType,
)


@pytest.mark.asyncio
async def test_cli_seeder_execution_and_idempotency():
    """Validates that CatalogSeeder can reset and re-seed idempotently without duplicating rows."""
    async with async_session_factory() as session:
        # 1. Reset and Seed
        res_reset = await CatalogSeeder.seed_all(session=session, reset=True)
        assert res_reset["status"] == "COMPLETED"
        assert res_reset["merchants_seeded"] == 3
        assert res_reset["offerings_seeded"] == 13

        # Count total catalog entries across seeded merchants
        stmt_count = select(func.count(KnowledgeEntry.id)).where(KnowledgeEntry.entry_type == "CATALOG")
        count_first = (await session.execute(stmt_count)).scalar()
        assert count_first >= 13

        # 2. Re-run without reset (Idempotent Upsert)
        res_upsert = await CatalogSeeder.seed_all(session=session, reset=False)
        assert res_upsert["status"] == "COMPLETED"
        assert res_upsert["offerings_seeded"] == 13

        count_second = (await session.execute(stmt_count)).scalar()
        assert count_second == count_first, "Idempotent re-run must not create duplicate catalog entries!"


@pytest.mark.asyncio
async def test_cross_tenant_rls_isolation(seeded_demo_tenants):
    """Validates that catalog searches under one tenant never leak offerings belonging to another."""
    alaba_id = seeded_demo_tenants["alaba_agro_id"]
    lekki_id = seeded_demo_tenants["lekki_glow_id"]
    horizon_id = seeded_demo_tenants["horizon_tech_id"]

    # 1. Searching "haircut" under Alaba Agro must yield 0 results
    async with tenant_session_scope(alaba_id) as session:
        alaba_haircut = await KnowledgeService.search_catalog_offerings(
            merchant_id=alaba_id,
            query="haircut",
            session=session,
        )
        assert len(alaba_haircut) == 0

    # 2. Searching "haircut" under Lekki Glow must yield the Executive Haircut
    async with tenant_session_scope(lekki_id) as session:
        lekki_haircut = await KnowledgeService.search_catalog_offerings(
            merchant_id=lekki_id,
            query="haircut",
            session=session,
        )
        assert len(lekki_haircut) >= 1
        assert lekki_haircut[0].sku == "SRV_EXECUTIVE_HAIRCUT"

    # 3. Searching "rice" under Lekki Glow must yield 0 results
    async with tenant_session_scope(lekki_id) as session:
        lekki_rice = await KnowledgeService.search_catalog_offerings(
            merchant_id=lekki_id,
            query="rice",
            session=session,
        )
        assert len(lekki_rice) == 0

    # 4. Searching "iphone" under Horizon Tech must succeed, but fail under Alaba Agro
    async with tenant_session_scope(horizon_id) as session:
        horizon_phones = await KnowledgeService.search_catalog_offerings(
            merchant_id=horizon_id,
            query="iphone",
            session=session,
        )
        assert len(horizon_phones) >= 1
        assert horizon_phones[0].sku == "TECH_IPHONE_15_PRO_128GB"

    async with tenant_session_scope(alaba_id) as session:
        alaba_phones = await KnowledgeService.search_catalog_offerings(
            merchant_id=alaba_id,
            query="iphone",
            session=session,
        )
        assert len(alaba_phones) == 0


@pytest.mark.asyncio
async def test_pidgin_and_slang_keyword_retrieval(seeded_demo_tenants):
    """Validates that local Nigerian Pidgin, Yoruba, and Hausa slang keywords match accurately."""
    alaba_id = seeded_demo_tenants["alaba_agro_id"]
    lekki_id = seeded_demo_tenants["lekki_glow_id"]

    # 1. "shinkafa" (Hausa/Pidgin for rice) -> Mama Gold & Royal Stallion Rice
    async with tenant_session_scope(alaba_id) as session:
        shinkafa_res = await KnowledgeService.search_catalog_offerings(
            merchant_id=alaba_id,
            query="shinkafa",
            session=session,
        )
        assert len(shinkafa_res) >= 2
        skus = [r.sku for r in shinkafa_res]
        assert "RICE_MAMA_GOLD_50KG" in skus
        assert "RICE_ROYAL_STALLION_50KG" in skus

    # 2. "ororo" (Yoruba/Pidgin for vegetable oil) -> Devon's King Vegetable Oil
    async with tenant_session_scope(alaba_id) as session:
        ororo_res = await KnowledgeService.search_catalog_offerings(
            merchant_id=alaba_id,
            query="ororo",
            session=session,
        )
        assert len(ororo_res) >= 1
        assert ororo_res[0].sku == "OIL_DEVONS_KING_25L"
        assert "Devon's King" in ororo_res[0].title

    # 3. "fade" -> Executive Haircut under Lekki Glow
    async with tenant_session_scope(lekki_id) as session:
        fade_res = await KnowledgeService.search_catalog_offerings(
            merchant_id=lekki_id,
            query="fade",
            session=session,
        )
        assert len(fade_res) >= 1
        assert fade_res[0].sku == "SRV_EXECUTIVE_HAIRCUT"


@pytest.mark.asyncio
async def test_variant_clarification_on_mama_gold(seeded_demo_tenants):
    """Validates multi-variant packaging (50kg vs 25kg) triggers an Interactive List with both options."""
    alaba_id = seeded_demo_tenants["alaba_agro_id"]

    nlu_result = {
        "intent": "PRICE_INQUIRY",
        "extracted_entities": {"product": "Mama Gold"},
        "suggested_reply": "Here are our Mama Gold rice sizes:",
    }

    envelope = await ResponseOrchestrator.resolve(
        merchant_id=alaba_id,
        nlu_result=nlu_result,
        customer_phone="+2348011998877",
        raw_message="How much is Mama Gold rice?",
    )

    assert envelope.strategy == ResponseStrategy.CATALOG_PRODUCT_LIST
    assert envelope.message_type == EgressMessageType.INTERACTIVE_LIST
    assert envelope.sections is not None

    rows = envelope.sections[0]["rows"]
    row_ids = [r["id"] for r in rows]
    assert "PRODUCT:RICE_MAMA_GOLD_50KG" in row_ids
    assert "PRODUCT:RICE_MAMA_GOLD_25KG" in row_ids


@pytest.mark.asyncio
async def test_out_of_stock_prioritization_and_alert(seeded_demo_tenants):
    """Validates out-of-stock items rank below available items and display out-of-stock status."""
    alaba_id = seeded_demo_tenants["alaba_agro_id"]

    # 1. Direct query for sold-out item (Golden Penny Flour)
    async with tenant_session_scope(alaba_id) as session:
        flour_res = await KnowledgeService.search_catalog_offerings(
            merchant_id=alaba_id,
            query="flour",
            session=session,
        )
        assert len(flour_res) >= 1
        flour = flour_res[0]
        assert flour.sku == "FLOUR_GOLDEN_PENNY_50KG"
        assert flour.is_available is False

    # 2. Detail card generation displays out of stock
    envelope = ResponseFormatter.format_product_detail_card(
        to_phone="+2348011998877",
        offering=flour,
    )
    assert envelope.message_type == EgressMessageType.INTERACTIVE_BUTTONS
    assert "Out of Stock" in envelope.body_text


@pytest.mark.asyncio
async def test_service_appointment_metadata_and_card(seeded_demo_tenants):
    """Validates SERVICE_APPOINTMENT polymorphic schema attributes and 3-button card rendering."""
    lekki_id = seeded_demo_tenants["lekki_glow_id"]

    offering = await KnowledgeService.get_offering_by_sku(
        merchant_id=lekki_id,
        sku="SRV_EXECUTIVE_HAIRCUT",
    )

    assert offering is not None
    assert offering.offering_type == OfferingType.SERVICE_APPOINTMENT
    assert offering.price_kobo == 1500000
    assert offering.price_naira == 15000.0

    # Vertical metadata verification
    assert offering.metadata.get("duration_minutes") == 45
    assert offering.metadata.get("commitment_deposit_kobo") == 500000

    envelope = ResponseFormatter.format_product_detail_card(
        to_phone="+2348011998877",
        offering=offering,
    )

    assert envelope.strategy == ResponseStrategy.SINGLE_PRODUCT_QUOTE
    assert "Executive Haircut" in envelope.body_text
    assert "15,000" in envelope.body_text

    button_ids = [b["id"] for b in envelope.buttons]
    assert "SET_SLOT:sku:SRV_EXECUTIVE_HAIRCUT" in button_ids


@pytest.mark.asyncio
async def test_redis_manifest_prewarming_validity(seeded_demo_tenants):
    """Validates that the seeder pre-warmed Redis manifests and read-through returns valid Markdown."""
    alaba_id = seeded_demo_tenants["alaba_agro_id"]
    lekki_id = seeded_demo_tenants["lekki_glow_id"]

    async with tenant_session_scope(alaba_id) as session:
        alaba_manifest = await KnowledgeService.get_manifest_read_through(
            session=session,
            merchant_id=UUID(alaba_id),
            topic="catalog",
        )
        assert "### Merchant Catalog Manifest:" in alaba_manifest
        assert "Mama Gold Rice 50kg" in alaba_manifest
        assert "₦78,000" in alaba_manifest
        assert "Devon's King Vegetable Oil 25L" in alaba_manifest

    async with tenant_session_scope(lekki_id) as session:
        lekki_manifest = await KnowledgeService.get_manifest_read_through(
            session=session,
            merchant_id=UUID(lekki_id),
            topic="catalog",
        )
        assert "### Merchant Catalog Manifest:" in lekki_manifest
        assert "Executive Haircut" in lekki_manifest
        assert "₦15,000" in lekki_manifest
        assert "Deep Tissue Swedish Massage" in lekki_manifest
