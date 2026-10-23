"""Integration & Unit Tests for Multi-Provider BSP Channel Abstraction & Local BSP Sandbox (ADR-0047)."""

import pytest
from httpx import AsyncClient

from app.adapters.whatsapp import (
    get_whatsapp_bsp_adapter,
    TermiiWhatsAppAdapter,
    TwilioWhatsAppAdapter,
    Dialog360WhatsAppAdapter,
    MockWhatsAppBSPAdapter,
)
from app.contexts.ingress.services import IngressService
from app.sandbox.state import get_sandbox_store


def test_multi_provider_adapter_registry_and_normalization():
    """Verifies BSPChannelAdapter resolution and inbound payload normalization across Meta, Termii, Twilio, and 360dialog."""
    # 1. Termii adapter normalization
    termii_adapter = get_whatsapp_bsp_adapter(provider_slug="termii")
    assert isinstance(termii_adapter, TermiiWhatsAppAdapter)
    termii_payload = {
        "device_id": "meta_phone_alaba_agro",
        "sender": "2348031234567",
        "contact_name": "Chinedu Okafor",
        "message_id": "termii_msg_001",
        "message": "How much be Dangote Sugar 50kg?",
    }
    termii_env = IngressService.normalize_inbound_payload(termii_payload, provider_slug="termii")
    assert termii_env.provider == "TERMII"
    assert termii_env.has_message is True
    assert termii_env.phone_number_id == "meta_phone_alaba_agro"
    assert termii_env.sender_phone == "2348031234567"
    assert termii_env.text == "How much be Dangote Sugar 50kg?"

    # 2. Twilio adapter normalization (including interactive ButtonPayload)
    twilio_adapter = get_whatsapp_bsp_adapter(provider_slug="twilio")
    assert isinstance(twilio_adapter, TwilioWhatsAppAdapter)
    twilio_payload = {
        "To": "whatsapp:meta_phone_alaba_agro",
        "From": "whatsapp:+2348031234567",
        "ProfileName": "Amina Bello",
        "MessageSid": "SM99887766",
        "Body": "Order Now",
        "ButtonPayload": "SET_SLOT:sku:RICE_MAMA_GOLD_50KG",
    }
    twilio_env = IngressService.normalize_inbound_payload(twilio_payload, provider_slug="twilio")
    assert twilio_env.provider == "TWILIO_AFRICA"
    assert twilio_env.has_message is True
    assert twilio_env.phone_number_id == "meta_phone_alaba_agro"
    assert twilio_env.is_interactive is True
    assert twilio_env.interactive_id == "SET_SLOT:sku:RICE_MAMA_GOLD_50KG"

    # 3. 360dialog adapter resolution
    d360_adapter = get_whatsapp_bsp_adapter(provider_slug="360dialog")
    assert isinstance(d360_adapter, Dialog360WhatsAppAdapter)


@pytest.mark.asyncio
async def test_parameterized_webhook_provider_routes(async_client: AsyncClient):
    """Verifies GET/POST /api/v1/ingress/webhooks/{provider} works for whatsapp, termii, twilio, and sandbox."""
    # Challenge verification on /webhooks/termii
    from app.core.config import settings
    res_challenge = await async_client.get(
        "/api/v1/ingress/webhooks/termii",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.META_WEBHOOK_VERIFY_TOKEN,
            "hub.challenge": "998877",
        },
    )
    assert res_challenge.status_code == 200
    assert res_challenge.text == "998877"

    # Termii webhook POST
    res_post = await async_client.post(
        "/api/v1/ingress/webhooks/termii",
        json={
            "device_id": "unknown_device_id",
            "sender": "2348031234567",
            "message": "How far",
        },
    )
    assert res_post.status_code == 200
    body = res_post.json()
    assert body["provider"] == "TERMII"


@pytest.mark.asyncio
async def test_sandbox_24h_window_governor_and_fault_injection(async_client: AsyncClient):
    """Verifies Local BSP Sandbox 24h Customer Service Window expiration and fault profile controls."""
    store = get_sandbox_store()
    await store.update_fault_profile({"clock_offset_hours": 0.0, "enforce_24h_window": True})
    await store.record_customer_inbound_turn("meta_phone_alaba_agro", "2348031234567")

    # 1. Window is initially open
    w_open = await store.check_customer_service_window("meta_phone_alaba_agro", "2348031234567")
    assert w_open["is_open"] is True

    # 2. Clock-shift +25 hours via /api/v1/sandbox/faults
    res_fault = await async_client.patch(
        "/api/v1/sandbox/faults",
        json={"clock_offset_hours": 25.0, "enforce_24h_window": True},
    )
    assert res_fault.status_code == 200
    w_expired = await store.check_customer_service_window("meta_phone_alaba_agro", "2348031234567")
    assert w_expired["is_open"] is False

    # 3. Attempting to send a free-form text message when window is expired logs a blocked system alert
    adapter = get_whatsapp_bsp_adapter(provider_slug="sandbox")
    send_res = await adapter.send_text_message(
        to_phone="2348031234567",
        message="This session message should be blocked by the 24h governor",
        phone_number_id="meta_phone_alaba_agro",
    )
    assert send_res["status"] == "FAILED_24H_WINDOW_EXPIRED"

    # 4. Sending an approved WhatsApp Template message succeeds even when 24h window is expired
    tpl_res = await async_client.post(
        "/api/v1/sandbox/send-template",
        json={
            "phone_number_id": "meta_phone_alaba_agro",
            "to_phone": "2348031234567",
            "template_name": "re_engagement_window_opener",
            "language_code": "en",
            "parameters": ["Tunde", "Alaba Agro"],
        },
    )
    assert tpl_res.status_code == 200
    assert tpl_res.json()["status"] == "TEMPLATE_SENT"

    # Reset clock offset
    await store.update_fault_profile({"clock_offset_hours": 0.0})


# -----------------------------------------------------------------------------
# MULTI-CHANNEL RESOLUTION & ANTI-SPOOFING SECURITY TESTS (ADR-0048)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inbound_resolution_primary_and_secondary_channels(seeded_demo_tenants: dict):
    """Verifies resolving both primary and secondary WhatsApp channels returns the owning merchant and channel context."""
    from app.contexts.core.services import MerchantIdentificationService
    from app.contexts.knowledge.seed_data import ALABA_AGRO_MERCHANT_ID

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
    from app.contexts.core.services import MerchantIdentificationService
    from app.contexts.knowledge.seed_data import ALABA_AGRO_MERCHANT_ID

    out_primary = await MerchantIdentificationService.resolve_outbound(
        merchant_id=str(ALABA_AGRO_MERCHANT_ID),
        requested_phone_id="meta_phone_alaba_agro",
    )
    assert out_primary.phone_number_id == "meta_phone_alaba_agro"
    assert out_primary.is_default is True

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
    from app.contexts.core.services import MerchantIdentificationService
    from app.contexts.knowledge.seed_data import ALABA_AGRO_MERCHANT_ID, LEKKI_GLOW_MERCHANT_ID

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
    import uuid
    from app.contexts.core.services import MerchantIdentificationService
    from app.contexts.knowledge.seed_data import ALABA_AGRO_MERCHANT_ID, HORIZON_TECH_MERCHANT_ID
    from app.core.exceptions import TenantChannelSecurityError
    from app.core.worker import _execute_webhook_processing

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
    import uuid
    from app.contexts.core.models import Merchant, MerchantChannel
    from app.contexts.core.services import MerchantIdentificationService
    from app.core.database import async_session_factory
    from app.core.exceptions import TenantChannelSecurityError

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
    """Verifies that an inbound turn on Alaba Agro's secondary line routes its outbound reply back out on that secondary line and updates conversation.channel_id."""
    from uuid import UUID
    from sqlalchemy import select
    from app.contexts.core.services import MerchantIdentificationService
    from app.contexts.ingress.models import Conversation
    from app.contexts.knowledge.seed_data import ALABA_AGRO_MERCHANT_ID
    from app.core.database import tenant_session_scope

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

    bot_messages = [
        m for m in body["messages"]
        if m["sender"] == "bot" and m["to_phone"] in ("+2348039998877", "2348039998877")
    ]
    assert len(bot_messages) >= 1
    assert bot_messages[-1]["phone_number_id"] == "meta_phone_alaba_agro_delivery"
    assert bot_messages[-1]["from_phone"] == "meta_phone_alaba_agro_delivery"

    # Verify ingress.conversations.channel_id FK tracks the active secondary channel and supports backtracking
    secondary_ctx = await MerchantIdentificationService.resolve_inbound("meta_phone_alaba_agro_delivery")
    assert secondary_ctx is not None and secondary_ctx.channel_id is not None

    async with tenant_session_scope(str(ALABA_AGRO_MERCHANT_ID)) as session:
        conv_res = await session.execute(
            select(Conversation).where(
                Conversation.merchant_id == ALABA_AGRO_MERCHANT_ID,
                Conversation.customer_phone.in_(["+2348039998877", "2348039998877"]),
            )
        )
        conv = conv_res.scalars().first()
        assert conv is not None
        assert str(conv.channel_id) == secondary_ctx.channel_id

        # Backtrack outbound channel from conversation.channel_id without requested_phone_id
        backtracked = await MerchantIdentificationService.resolve_outbound(
            merchant_id=str(ALABA_AGRO_MERCHANT_ID),
            channel_id=str(conv.channel_id),
            db=session,
        )
        assert backtracked.phone_number_id == "meta_phone_alaba_agro_delivery"
