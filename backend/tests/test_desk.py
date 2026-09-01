"""Tests for Agent Desk Context Synthesis and Zero-Repeat Handoffs."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_generate_six_field_context_card(async_client: AsyncClient):
    """Verifies that the 6-field context card synthesizes executive summary and suggested reply."""
    payload = {
        "customer_name": "Chidinma Okafor",
        "customer_phone": "+2348023456789",
        "chat_history": [
            "Customer: How much is 10 cartons of sunflower cooking oil?",
            "Bot: ₦22,000 per carton.",
            "Customer: Abeg can I pay on delivery to Victoria Island?",
        ],
    }
    response = await async_client.post("/api/v1/desk/context", json=payload)
    assert response.status_code == 200
    resp_body = response.json()
    assert resp_body["success"] is True
    data = resp_body["data"]
    assert data["status"] == "CONTEXT_INJECTED"
    summary = data["summary"]
    assert "executiveSummary" in summary
    assert "detectedBudgetNaira" in summary
    assert "suggestedFirstResponse" in summary
    assert summary["urgencyTier"] in ["HOT", "WARM"]

