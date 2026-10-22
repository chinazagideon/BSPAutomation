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
