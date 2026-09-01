"""Tests for Checkout Carts, 4-Leg Double Entry Ledger, and Accounting Validation."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ledger_validation_balanced(async_client: AsyncClient):
    """Verifies that a balanced ledger equation returns SETTLED_BALANCED."""
    payload = {
        "assets": 150000.0,
        "liabilities": 50000.0,
        "equity": 100000.0,
        "transaction_ref": "TXN_NG_9812",
        "received_amount": 45000.0,
        "expected_amount": 45000.0,
    }
    response = await async_client.post("/api/v1/ledger/validate", json=payload)
    assert response.status_code == 200
    resp_body = response.json()
    assert resp_body["success"] is True
    data = resp_body["data"]
    assert data["isBalanced"] is True
    assert data["isAmountMatched"] is True
    assert data["status"] == "SETTLED_BALANCED"


@pytest.mark.asyncio
async def test_ledger_validation_imbalance_alert(async_client: AsyncClient):
    """Verifies that an unbalanced equation returns MISMATCH_ALERT with AI explanation."""
    payload = {
        "assets": 120000.0,
        "liabilities": 50000.0,
        "equity": 100000.0,  # Imbalance: 120,000 != 150,000
        "transaction_ref": "TXN_NG_9812",
        "received_amount": 45000.0,
        "expected_amount": 45000.0,
    }
    response = await async_client.post("/api/v1/ledger/validate", json=payload)
    assert response.status_code == 200
    resp_body = response.json()
    assert resp_body["success"] is True
    data = resp_body["data"]
    assert data["isBalanced"] is False
    assert data["status"] == "MISMATCH_ALERT"
    assert data["aiExplanation"] is not None

