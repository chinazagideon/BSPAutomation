"""Unit & Integration Tests for MerchantIdentificationService & 1:N Multi-Channel Resolution (ADR-0048)."""

import uuid
import pytest
from httpx import AsyncClient

from app.contexts.core.channel_service import MerchantIdentificationService
from app.contexts.core.models import Merchant, MerchantChannel
from app.contexts.knowledge.seed_data import (
    ALABA_AGRO_MERCHANT_ID,
    LEKKI_GLOW_MERCHANT_ID,
    HORIZON_TECH_MERCHANT_ID,
)
from app.core.database import async_session_factory
from app.core.exceptions import TenantChannelSecurityError
from app.core.worker import _execute_webhook_processing


@pytest.mark.asyncio
async def test_inbound_resolution_primary_and_secondary_channels(seeded_demo_tenants: dict):
    """Verifies resolving both primary and secondary WhatsApp channels returns the owning merchant and channel context."""
    MerchantIdentificationService.invalidate_cache()

    # 1. Primary channel for Alaba Agro
    primary_ctx = await MerchantIdentificationService.resolve_inbound("meta_phone_alaba_agro")
    assert primary_ctx is not None
    assert primary_ctx.merchant_id == str(ALABA_AGRO_MERCHANT_ID)
    assert primary_ctx.phone_number_id == "meta_phone_alaba_agro"
    assert primary_ctx.business_phone == "+2348011223301"
    assert primary_ctx.channel_label == "Main Retail Desk"
    assert primary_ctx.is_default is True
    assert primary_ctx.is_active is True

    # 2. Secondary channel for Alaba Agro (1:N multi-channel)
    secondary_ctx = await MerchantIdentificationService.resolve_inbound("meta_phone_alaba_agro_delivery")
    assert secondary_ctx is not None
    assert secondary_ctx.merchant_id == str(ALABA_AGRO_MERCHANT_ID)
    assert secondary_ctx.phone_number_id == "meta_phone_alaba_agro_delivery"
    assert secondary_ctx.business_phone == "+2348011223399"
    assert secondary_ctx.channel_label == "Wholesale & Logistics Desk"
    assert secondary_ctx.is_default is False
    assert secondary_ctx.is_active is True

    # 3. E.164 business phone lookup for secondary channel
    e164_ctx = await MerchantIdentificationService.resolve_inbound("+2348011223399")
    assert e164_ctx is not None
    assert e164_ctx.merchant_id == str(ALABA_AGRO_MERCHANT_ID)
    assert e164_ctx.phone_number_id == "meta_phone_alaba_agro_delivery"


@pytest.mark.asyncio
async def test_outbound_resolution_with_valid_requested_channel(seeded_demo_tenants: dict):
    """Verifies explicit requested channel ID is authorized and returned when owned by the merchant."""
    # Requesting primary channel
    out_primary = await MerchantIdentificationService.resolve_outbound(
        merchant_id=str(ALABA_AGRO_MERCHANT_ID),
        requested_phone_id="meta_phone_alaba_agro",
    )
    assert out_primary.phone_number_id == "meta_phone_alaba_agro"
    assert out_primary.is_default is True

    # Requesting secondary channel owned by Alaba Agro
    out_secondary = await MerchantIdentificationService.resolve_outbound(
        merchant_id=str(ALABA_AGRO_MERCHANT_ID),
        requested_phone_id="meta_phone_alaba_agro_delivery",
    )
    assert out_secondary.phone_number_id == "meta_phone_alaba_agro_delivery"
    assert out_secondary.channel_label == "Wholesale & Logistics Desk"
    assert out_secondary.is_default is False


@pytest.mark.asyncio
async def test_outbound_resolution_default_when_none_requested(seeded_demo_tenants: dict):
    """Verifies proactive outbound without phone_number_id dynamically resolves the merchant's is_default=True channel."""
    default_ctx = await MerchantIdentificationService.resolve_outbound(
        merchant_id=str(ALABA_AGRO_MERCHANT_ID),
        requested_phone_id=None,
    )
    assert default_ctx is not None
    assert default_ctx.merchant_id == str(ALABA_AGRO_MERCHANT_ID)
    assert default_ctx.phone_number_id == "meta_phone_alaba_agro"
    assert default_ctx.is_default is True

    lekki_default = await MerchantIdentificationService.resolve_outbound(
        merchant_id=str(LEKKI_GLOW_MERCHANT_ID),
        requested_phone_id=None,
    )
    assert lekki_default.phone_number_id == "meta_phone_lekki_glow"
    assert lekki_default.is_default is True


@pytest.mark.asyncio
async def test_outbound_anti_spoofing_fail_closed(seeded_demo_tenants: dict):
    """Verifies that passing Tenant B's phone_number_id while dispatching for Tenant A raises TenantChannelSecurityError."""
    # Attempting to use Lekki Glow's channel from Alaba Agro tenant context
    with pytest.raises(TenantChannelSecurityError) as exc_info:
        await MerchantIdentificationService.resolve_outbound(
            merchant_id=str(ALABA_AGRO_MERCHANT_ID),
            requested_phone_id="meta_phone_lekki_glow",
        )
    assert exc_info.value.merchant_id == str(ALABA_AGRO_MERCHANT_ID)
    assert exc_info.value.phone_number_id == "meta_phone_lekki_glow"

    # Attempting to use an unregistered random phone_number_id from Horizon Tech tenant context
    with pytest.raises(TenantChannelSecurityError):
        await MerchantIdentificationService.resolve_outbound(
            merchant_id=str(HORIZON_TECH_MERCHANT_ID),
            requested_phone_id="unregistered_rogue_channel_999",
        )

    # Worker execution with spoofed payload phone_number_id for Alaba Agro must also raise TenantChannelSecurityError
    spoofed_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_SPOOF",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "meta_phone_lekki_glow"},
                    "contacts": [{"profile": {"name": "Spoof Caller"}, "wa_id": "2348031234567"}],
                    "messages": [{
                        "from": "2348031234567",
                        "id": f"wamid.spoof.{uuid.uuid4().hex[:8]}",
                        "timestamp": "1725360000",
                        "type": "text",
                        "text": {"body": "How much be rice?"},
                    }],
                },
                "field": "messages",
            }],
        }],
    }
    with pytest.raises(TenantChannelSecurityError):
        await _execute_webhook_processing(
            ctx={},
            merchant_id=str(ALABA_AGRO_MERCHANT_ID),
            raw_payload=spoofed_payload,
            provider_slug="sandbox",
        )


@pytest.mark.asyncio
async def test_outbound_inactive_channel_rejection():
    """Verifies that deactivated channels raise TenantChannelSecurityError on outbound and return None on inbound."""
    suffix = uuid.uuid4().hex[:8]
    inactive_phone_id = f"meta_phone_inactive_{suffix}"
    m_id = uuid.uuid4()

    async with async_session_factory() as session:
        merchant = Merchant(
            id=m_id,
            business_name=f"Inactive Channel Test {suffix}",
            slug=f"inactive-ch-{suffix}",
            whatsapp_business_phone=f"+23489{suffix[:8]}",
            whatsapp_phone_number_id=inactive_phone_id,
            is_active=True,
        )
        session.add(merchant)
        await session.flush()

        channel = MerchantChannel(
            merchant_id=m_id,
            phone_number_id=inactive_phone_id,
            business_phone=f"+23489{suffix[:8]}",
            provider="META_CLOUD",
            channel_label="Decommissioned Support Line",
            is_default=True,
            is_active=False,
        )
        session.add(channel)
        await session.commit()

    MerchantIdentificationService.invalidate_cache(inactive_phone_id)

    # 1. Inbound lookup on deactivated channel must return None
    inbound_res = await MerchantIdentificationService.resolve_inbound(inactive_phone_id)
    assert inbound_res is None

    # 2. Explicit outbound lookup on deactivated channel must raise TenantChannelSecurityError
    with pytest.raises(TenantChannelSecurityError) as exc_explicit:
        await MerchantIdentificationService.resolve_outbound(
            merchant_id=str(m_id),
            requested_phone_id=inactive_phone_id,
        )
    assert "deactivated" in exc_explicit.value.reason.lower()

    # 3. Default outbound lookup when all channels are deactivated must raise TenantChannelSecurityError
    with pytest.raises(TenantChannelSecurityError) as exc_default:
        await MerchantIdentificationService.resolve_outbound(
            merchant_id=str(m_id),
            requested_phone_id=None,
        )
    assert "deactivated" in exc_default.value.reason.lower()


@pytest.mark.asyncio
async def test_multi_channel_end_to_end_egress_routing(async_client: AsyncClient, seeded_demo_tenants: dict):
    """Verifies that an inbound turn on Alaba Agro's secondary line routes its outbound reply back out on that secondary line."""
    res = await async_client.post(
        "/api/v1/sandbox/inbound",
        json={
            "provider": "sandbox",
            "phone_number_id": "meta_phone_alaba_agro_delivery",
            "customer_phone": "+2348039998877",
            "customer_name": "Musa Danjuma",
            "message_type": "text",
            "text": "How much be Mama Gold Rice 50kg?",
            "execute_worker_inline": True,
        },
    )
    assert res.status_code == 200
    raw_json = res.json()
    body = raw_json.get("data", raw_json)
    assert body["status"] == "OK"
    assert body["worker_result"]["status"] == "PROCESSED"

    # Verify the bot reply in sandbox messages was dispatched from meta_phone_alaba_agro_delivery
    bot_messages = [
        m for m in body["messages"]
        if m["sender"] == "bot" and m["to_phone"] in ("+2348039998877", "2348039998877")
    ]
    assert len(bot_messages) >= 1
    assert bot_messages[-1]["phone_number_id"] == "meta_phone_alaba_agro_delivery"
    assert bot_messages[-1]["from_phone"] == "meta_phone_alaba_agro_delivery"
