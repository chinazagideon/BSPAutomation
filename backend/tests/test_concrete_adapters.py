"""Unit & Integration Tests for Concrete LLM and ONNX Classifier Adapters (ADR-0044)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.adapters.custom_classifier import (
    LexicalDialectAnalyzer,
    ONNXClassifierAdapter,
    MockCustomClassifierAdapter,
)
from app.adapters.llm import GeminiFlashAdapter, MockLLMAdapter
from app.adapters.base import ClassificationOutput
from app.core.generation.ports import ExecutionPolicy


def test_lexical_dialect_analyzer():
    """Validates deterministic detection of Nigerian Pidgin, Commercial Slang, and English."""
    assert LexicalDialectAnalyzer.detect_dialect("Abeg wetin be your wholesale price?") == "Nigerian Pidgin"
    assert LexicalDialectAnalyzer.detect_dialect("How far, no wahala make we talk.") == "Nigerian Pidgin"
    assert LexicalDialectAnalyzer.detect_dialect("Oya drop am for my shop.") == "Nigerian Pidgin"
    assert LexicalDialectAnalyzer.detect_dialect("Please send me your acct details.") == "Commercial Slang"
    assert LexicalDialectAnalyzer.detect_dialect("What is the last price for this order?") == "Commercial Slang"
    assert LexicalDialectAnalyzer.detect_dialect("Please provide information regarding enterprise procurement.") == "Standard English"


@pytest.mark.asyncio
async def test_onnx_classifier_missing_model_fallback():
    """Validates graceful delegation to Mock adapter when ONNX model files are absent."""
    adapter = ONNXClassifierAdapter(model_path="models/non_existent_path")
    assert adapter._ensure_loaded() is False

    result = await adapter.classify("slash price if i buy plenty")
    assert isinstance(result, ClassificationOutput)
    assert result.intent == "WHOLESALE_DISCOUNT_INQUIRY"
    assert result.lead_tier == "HOT"
    assert result.tokens_consumed == 0
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_gemini_flash_adapter_missing_client_fallback():
    """Validates that GeminiFlashAdapter falls back to desk handoff if client is not configured."""
    adapter = GeminiFlashAdapter(api_key="", model_name="gemini-3.7-flash")
    result = await adapter.generate_chat_completion(
        prompt="Customer Message: Can we get a discount?",
        system_instruction="Classify intent",
    )
    assert isinstance(result, ClassificationOutput)
    assert result.action == "DISPATCH_AGENT_HANDOFF"
    assert result.tokens_consumed == 0
    assert result.extracted_entities.get("error_fallback") is True


@pytest.mark.asyncio
async def test_gemini_flash_adapter_success_with_token_metering():
    """Validates response parsing and real token metering from Gemini usage_metadata."""
    adapter = GeminiFlashAdapter(api_key="test_dummy_key", model_name="gemini-3.7-flash")

    # Mock client and response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.usage_metadata = MagicMock()
    mock_response.usage_metadata.total_token_count = 215

    payload_json = (
        '{"intent": "COMPLEX_CONSULTATION", "lead_tier": "WARM", '
        '"urgency_score": 7, "confidence": 0.96, "detected_dialect": "Nigerian Pidgin", '
        '"suggested_reply": "No wahala! We go review am.", "action": "NURTURE_OR_DEEP_RAG", '
        '"extracted_entities": {"topic": "SLA"}}'
    )
    mock_response.text = payload_json
    mock_response.parsed = None

    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
    adapter._client = mock_client

    result = await adapter.generate_chat_completion(
        prompt="Customer Message: We need a custom SLA",
        system_instruction="Classify intent",
    )

    assert result.intent == "COMPLEX_CONSULTATION"
    assert result.lead_tier == "WARM"
    assert result.tokens_consumed == 215
    assert result.suggested_reply == "No wahala! We go review am."
    assert result.extracted_entities.get("topic") == "SLA"


@pytest.mark.asyncio
async def test_gemini_flash_adapter_api_error_fallback():
    """Validates that API errors (e.g. 429 quota or 404 model) result in instant desk handoff with 0 tokens."""
    adapter = GeminiFlashAdapter(api_key="test_dummy_key", model_name="gemini-3.7-flash")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=Exception("429 Resource has been exhausted"))
    adapter._client = mock_client

    result = await adapter.generate_chat_completion(
        prompt="Customer Message: Hello",
        system_instruction="Classify intent",
    )

    assert result.action == "DISPATCH_AGENT_HANDOFF"
    assert result.tokens_consumed == 0
    assert result.confidence == 0.50
    assert result.extracted_entities.get("error_fallback") is True
    assert "429" in result.extracted_entities.get("reason", "")


@pytest.mark.asyncio
async def test_ingress_classification_policy_override(async_client, default_merchant_headers):
    """Validates that policy='DEEP_REASONING' bypasses Stage 1 Fast-Path even on high-frequency greetings."""
    # With CASCADING_FALLBACK or default, 'how far' matches Fast-Path (Stage 1)
    res_fast = await async_client.post(
        "/api/v1/ingress/classify",
        headers=default_merchant_headers,
        json={"message": "how far", "policy": "FASTEST_PATH"},
    )
    assert res_fast.status_code == 200
    data_fast = res_fast.json()["data"]
    assert data_fast["routingSource"] == "FAST_PATH"
    assert data_fast["tokensConsumed"] == 0

    # With policy='DEEP_REASONING', it bypasses Stage 1 and Stage 2, escalating to Stage 3
    res_deep = await async_client.post(
        "/api/v1/ingress/classify",
        headers=default_merchant_headers,
        json={"message": "how far", "policy": "DEEP_REASONING"},
    )
    assert res_deep.status_code == 200
    data_deep = res_deep.json()["data"]
    assert data_deep["routingSource"] == "GEMINI_LLM_ESCALATION"
    assert data_deep["tokensConsumed"] > 0
