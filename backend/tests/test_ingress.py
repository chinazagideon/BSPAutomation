"""Tests for Ingress Webhook Verification and HTTP Endpoints."""

import pytest
from httpx import AsyncClient
from app.core.config import settings


@pytest.mark.asyncio
async def test_whatsapp_webhook_verification_challenge(async_client: AsyncClient):
    """Verifies Meta Cloud API Webhook subscription challenge verification."""
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": settings.META_WEBHOOK_VERIFY_TOKEN,
        "hub.challenge": "1158201444",
    }
    response = await async_client.get("/api/v1/ingress/webhooks/whatsapp", params=params)
    assert response.status_code == 200
    assert response.text == "1158201444"


@pytest.mark.asyncio
async def test_ingress_classify_endpoint(async_client: AsyncClient, default_merchant_headers: dict):
    """Verifies the /api/v1/ingress/classify endpoint executes the cascading pipeline."""
    payload = {
        "message": "I wan order 5 cartons of cooking oil deliver to Ikeja",
        "customer_phone": "+2348031234567",
        "customer_name": "Emeka Obi",
    }
    response = await async_client.post(
        "/api/v1/ingress/classify",
        json=payload,
        headers=default_merchant_headers,
    )
    assert response.status_code == 200
    resp_body = response.json()
    assert resp_body["success"] is True
    data = resp_body["data"]
    assert data["routingSource"] in ["FAST_PATH", "CUSTOM_LOCAL_MODEL"]
    assert data["leadTier"] == "HOT"
    assert "extractedEntities" in data


@pytest.mark.asyncio
async def test_resolve_merchant_from_phone_duplicate_resilience():
    """Verifies resolve_merchant_from_phone gracefully handles multiple matching rows without MultipleResultsFound."""
    import uuid
    from datetime import datetime, timezone
    from app.core.database import async_session_factory
    from app.contexts.core.models import Merchant
    from app.core.tenant import resolve_merchant_from_phone, invalidate_phone_tenant_cache

    shared_phone_id = f"test_dup_{uuid.uuid4().hex[:8]}"
    m1_id = uuid.uuid4()
    m2_id = uuid.uuid4()

    async with async_session_factory() as session:
        # Create an older, inactive merchant
        m1 = Merchant(
            id=m1_id,
            business_name="Old Test Merchant",
            slug=f"old-merchant-{uuid.uuid4().hex[:6]}",
            whatsapp_business_phone="+2348000000001",
            whatsapp_phone_number_id=shared_phone_id,
            is_active=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        # Create a newer, active merchant
        m2 = Merchant(
            id=m2_id,
            business_name="Active Test Merchant",
            slug=f"active-merchant-{uuid.uuid4().hex[:6]}",
            whatsapp_business_phone="+2348000000002",
            whatsapp_phone_number_id=shared_phone_id,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add_all([m1, m2])
        await session.commit()

    invalidate_phone_tenant_cache(shared_phone_id)

    # Resolution should return active merchant (m2) and NOT raise MultipleResultsFound
    resolved = await resolve_merchant_from_phone(shared_phone_id)
    assert resolved == str(m2_id)


@pytest.mark.asyncio
async def test_whatsapp_webhook_payload_ingest(async_client: AsyncClient):
    """Verifies that an incoming Meta Cloud webhook payload is fast-ACKed and queued."""
    from app.core.tenant import resolve_merchant_from_phone

    # Ensure Alaba Agro phone is resolvable
    resolved_id = await resolve_merchant_from_phone("1291082787422067")
    assert resolved_id is not None

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "2973314499687426",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "2348011223301",
                                "phone_number_id": "1291082787422067",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test Customer"},
                                    "wa_id": "2348123456789",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "2348123456789",
                                    "id": f"wamid.test_{uuid_str()}",
                                    "timestamp": "1727890000",
                                    "type": "text",
                                    "text": {"body": "How much be Mama Gold rice 50kg?"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    response = await async_client.post(
        "/api/v1/ingress/webhooks/whatsapp",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "EVENT_RECEIVED"
    assert "event_id" in data
    assert "job_id" in data


def uuid_str():
    import uuid
    return uuid.uuid4().hex[:12]


