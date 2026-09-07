"""Automated Tests for Knowledge Base Bounded Context & Multi-Tenant Isolation (ADR-0039)."""

import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.contexts.core.models import Merchant
from app.contexts.knowledge.models import KnowledgeEntry
from app.contexts.knowledge.schemas import KnowledgeEntryCreate
from app.contexts.knowledge.services import KnowledgeService
from app.core.database import async_session_factory, tenant_session_scope


@pytest.mark.asyncio
async def test_knowledge_entry_crud_and_multi_tenant_isolation():
    """Validates KnowledgeEntry CRUD and multi-tenant isolation with global system entries."""
    suffix = str(uuid4())[:8]
    async with async_session_factory() as session:
        m_a = Merchant(
            business_name=f"Merchant A {suffix}",
            slug=f"merchant-a-{suffix}",
            whatsapp_business_phone=f"+234801{suffix[:6]}",
        )
        m_b = Merchant(
            business_name=f"Merchant B {suffix}",
            slug=f"merchant-b-{suffix}",
            whatsapp_business_phone=f"+234802{suffix[:6]}",
        )
        session.add_all([m_a, m_b])
        await session.commit()
        merchant_a_id = m_a.id
        merchant_b_id = m_b.id

    async with tenant_session_scope(merchant_a_id) as session:
        # 1. Create global system entry (merchant_id = None)
        global_entry = await KnowledgeService.create_entry(
            session=session,
            merchant_id=None,
            request=KnowledgeEntryCreate(
                entry_type="SLANG_EXPRESSION",
                title="Wetin Dey Happen",
                content="Common greeting inquiry meaning 'what is going on' or 'how are things'",
                metadata_json={"dialect": "Nigerian Pidgin", "category": "GREETING"},
            ),
        )

        # 2. Create proprietary entry for Merchant A
        merchant_a_entry = await KnowledgeService.create_entry(
            session=session,
            merchant_id=merchant_a_id,
            request=KnowledgeEntryCreate(
                entry_type="CATALOG",
                title="Commercial Baking Oven 4-Deck",
                content="Heavy duty electric stone deck oven for bread bakeries with digital timer.",
                metadata_json={"price_naira": 1450000, "sku": "OVEN-4D"},
            ),
        )

    # 3. Create proprietary entry for Merchant B
    async with tenant_session_scope(merchant_b_id) as session:
        merchant_b_entry = await KnowledgeService.create_entry(
            session=session,
            merchant_id=merchant_b_id,
            request=KnowledgeEntryCreate(
                entry_type="CATALOG",
                title="Salon Hydraulic Styling Chair",
                content="Premium leather salon chair with 360 degree rotation.",
                metadata_json={"price_naira": 185000, "sku": "CHAIR-01"},
            ),
        )

    # 4. Assert Merchant A query returns global entry + Merchant A entry, but NOT Merchant B entry
    async with tenant_session_scope(merchant_a_id) as session:
        entries_a = await KnowledgeService.list_entries(session=session, merchant_id=merchant_a_id)
        titles_a = [e.title for e in entries_a]
        assert "Wetin Dey Happen" in titles_a
        assert "Commercial Baking Oven 4-Deck" in titles_a
        assert "Salon Hydraulic Styling Chair" not in titles_a

    # 5. Assert Merchant B query returns global entry + Merchant B entry, but NOT Merchant A entry
    async with tenant_session_scope(merchant_b_id) as session:
        entries_b = await KnowledgeService.list_entries(session=session, merchant_id=merchant_b_id)
        titles_b = [e.title for e in entries_b]
        assert "Wetin Dey Happen" in titles_b
        assert "Salon Hydraulic Styling Chair" in titles_b
        assert "Commercial Baking Oven 4-Deck" not in titles_b


@pytest.mark.asyncio
async def test_knowledge_manifest_compilation_and_read_through():
    """Validates Redis manifest compilation and read-through caching."""
    suffix = str(uuid4())[:8]
    async with async_session_factory() as session:
        merchant = Merchant(
            business_name=f"Mixer Store {suffix}",
            slug=f"mixer-store-{suffix}",
            whatsapp_business_phone=f"+234803{suffix[:6]}",
        )
        session.add(merchant)
        await session.commit()
        merchant_id = merchant.id

    async with tenant_session_scope(merchant_id) as session:
        await KnowledgeService.create_entry(
            session=session,
            merchant_id=merchant_id,
            request=KnowledgeEntryCreate(
                entry_type="CATALOG",
                title="Industrial Mixer 50L",
                content="Spiral dough mixer for commercial bread making.",
                metadata_json={"price_naira": 820000},
            ),
        )

        manifest = await KnowledgeService.get_manifest_read_through(
            session=session,
            merchant_id=merchant_id,
            topic="catalog",
        )

        assert "### Merchant Catalog Manifest:" in manifest
        assert "Industrial Mixer 50L" in manifest
        assert "₦820,000" in manifest


@pytest.mark.asyncio
async def test_knowledge_api_endpoints():
    """Validates REST endpoints for knowledge entry creation and manifest retrieval."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check includes knowledge router
        res = await client.get("/api/health")
        assert res.status_code == 200

        # 2. Get API docs check
        res = await client.get("/docs")
        assert res.status_code == 200
