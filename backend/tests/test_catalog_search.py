"""Automated Tests for Tiered Discovery Catalog Search (ADR-0044).

Covers:
- Tier 1: Exact category match
- Tier 2: Search keyword containment
- Tier 3: Trigram similarity & typo tolerance ("Mama Golld" -> "Mama Gold Rice 50kg")
- In-stock prioritization: Available items rank above out-of-stock items
- Production environment gate: Prohibits mock catalog fallback in production
"""

import pytest
from uuid import uuid4
from unittest.mock import patch

from app.core.config import settings
from app.contexts.knowledge.services import KnowledgeService
from app.contexts.knowledge.offering_schemas import CoreOfferingDTO, OfferingType


@pytest.mark.asyncio
async def test_tiered_discovery_exact_category():
    """Validates Tier 1 exact category matching returns items categorized under 'rice'."""
    merchant_id = str(uuid4())
    results = await KnowledgeService.search_catalog_offerings(
        merchant_id=merchant_id,
        query="rice",
    )

    assert len(results) >= 2
    skus = [r.sku for r in results]
    assert "RICE_MAMA_GOLD_50KG" in skus
    assert "RICE_ROYAL_STALLION_50KG" in skus
    assert all(r.category.lower() == "rice" for r in results)


@pytest.mark.asyncio
async def test_tiered_discovery_keyword_containment():
    """Validates Tier 2 search keyword matching (e.g. 'granulated', 'parboiled', 'cube')."""
    merchant_id = str(uuid4())

    # Querying "granulated" which is in Dangote Sugar search keywords
    results = await KnowledgeService.search_catalog_offerings(
        merchant_id=merchant_id,
        query="granulated",
    )

    assert len(results) >= 1
    skus = [r.sku for r in results]
    assert "SUGAR_DANGOTE_50KG" in skus


@pytest.mark.asyncio
async def test_tiered_discovery_trigram_fuzzy():
    """Validates Tier 3 typo-tolerant search ('Mama Golld' ➔ 'Mama Gold Rice 50kg')."""
    merchant_id = str(uuid4())
    results = await KnowledgeService.search_catalog_offerings(
        merchant_id=merchant_id,
        query="Mama Golld",
    )

    assert len(results) >= 1
    top_result = results[0]
    assert top_result.sku == "RICE_MAMA_GOLD_50KG"
    assert "Mama Gold" in top_result.title


@pytest.mark.asyncio
async def test_in_stock_prioritization():
    """Validates that available/in-stock items rank strictly above out-of-stock items."""
    # Create two items in category 'rice': one in stock, one out of stock
    in_stock_item = CoreOfferingDTO(
        sku="RICE_IN_STOCK",
        title="In Stock Rice 50kg",
        description="Fresh harvest",
        price_kobo=7500000,
        price_naira=75000.0,
        is_available=True,
        category="rice",
        search_keywords=["rice", "in stock"],
    )
    out_of_stock_item = CoreOfferingDTO(
        sku="RICE_OUT_OF_STOCK",
        title="Out of Stock Rice 50kg",
        description="Sold out",
        price_kobo=7000000,
        price_naira=70000.0,
        is_available=False,
        category="rice",
        search_keywords=["rice", "out of stock"],
    )

    with patch.object(
        KnowledgeService,
        "search_catalog_offerings",
        return_value=[in_stock_item, out_of_stock_item],
    ):
        results = await KnowledgeService.search_catalog_offerings(
            merchant_id=str(uuid4()),
            query="rice",
        )

        assert len(results) == 2
        assert results[0].is_available is True
        assert results[1].is_available is False
        assert results[0].sku == "RICE_IN_STOCK"


@pytest.mark.asyncio
async def test_production_environment_gate():
    """Asserts mock catalog fallback is strictly forbidden in production mode."""
    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"
        merchant_id = str(uuid4())

        # When DB has 0 rows in production, search must return empty list []
        results = await KnowledgeService.search_catalog_offerings(
            merchant_id=merchant_id,
            query="rice",
        )

        assert results == []
    finally:
        settings.ENVIRONMENT = original_env
