"""Order ledger: stack-independent order references survive negotiation frame eviction."""

import pytest

from app.core.generation.order_ledger import CustomerOrderLedger


@pytest.mark.asyncio
async def test_ledger_records_and_lists_newest_first():
    merchant_id = "018f6c5a-8b1e-7230-a890-111111111111"
    phone = "+2348000000001"

    await CustomerOrderLedger.record_order(
        merchant_id, phone,
        {"quantity": 1, "product_name": "Dangote Sugar 50kg", "delivery_zone": "Ikeja", "fulfillment_type": "EXPRESS_DELIVERY"},
        total_kobo=8400000,
    )
    await CustomerOrderLedger.record_order(
        merchant_id, phone,
        {"line_items": [{}, {}], "product_name": "1x Sugar + 1x Rice", "delivery_zone": "Lekki"},
        total_kobo=12750000,
    )

    orders = await CustomerOrderLedger.list_recent(merchant_id, phone)
    assert [o.delivery_zone for o in orders][:2] == ["Lekki", "Ikeja"]
    assert orders[0].order_summary == "1x Sugar + 1x Rice"


@pytest.mark.asyncio
async def test_ledger_empty_for_unknown_customer():
    assert await CustomerOrderLedger.list_recent("018f6c5a-8b1e-7230-a890-111111111111", "+2340000000000") == []
