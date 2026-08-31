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
    data = response.json()
    assert data["routing_source"] in ["FAST_PATH", "CUSTOM_LOCAL_MODEL"]
    assert data["lead_tier"] == "HOT"
    assert "extracted_entities" in data
