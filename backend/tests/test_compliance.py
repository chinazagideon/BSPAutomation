"""Tests for Compliance PII Sanitization (BVN, NIN, NUBAN, Card PAN)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_pii_sanitization_masks_bvn_and_card(async_client: AsyncClient):
    """Verifies that BVN and Debit Card PAN are redacted with keyed tokens."""
    payload = {
        "text": "My BVN is 22298765432 and my card number is 5399 4100 2938 1204, please charge my account 0123456789"
    }
    response = await async_client.post("/api/v1/compliance/sanitize", json=payload)
    assert response.status_code == 200
    data = response.json()
    sanitized = data["sanitized_text"]

    # Assert raw sensitive numbers are NOT present in output
    assert "22298765432" not in sanitized
    assert "5399 4100 2938 1204" not in sanitized
    assert "0123456789" not in sanitized

    # Assert redaction tokens are inserted
    assert "[REDACTED_BVN_5432]" in sanitized
    assert "[REDACTED_CARD_PAN_1204]" in sanitized
    assert "[REDACTED_NUBAN_6789]" in sanitized
    assert len(data["redacted_entities"]) >= 3
