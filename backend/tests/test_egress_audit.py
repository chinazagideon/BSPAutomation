"""Tests for the Centralized Audited Egress Gateway, Wire Audit Invariants, and Typed ACL DTOs."""

import pytest
import json
import httpx
from pydantic import BaseModel, Field

from app.core.egress import (
    AuditedHttpClient,
    EgressAuditEvent,
    mask_sensitive_headers,
    sanitize_wire_payload,
)
from app.core.trace import set_trace_id, get_trace_id
from app.core.events import event_bus
from app.core.exceptions import (
    WhatsAppRateLimitedException,
    PaymentGatewayDeclinedException,
    ProviderSchemaMismatchException,
)
from app.adapters.moniepoint import (
    MoniepointCreateAccountResponseDTO,
    MoniepointAdapter,
)


class SampleExpectedResponseDTO(BaseModel):
    accountNumber: str = Field(..., min_length=10, max_length=10)
    accountName: str
    status: str


@pytest.mark.asyncio
async def test_egress_client_wire_audit_and_dto_hydration():
    """Verifies that AuditedHttpClient redacts secrets/PII, computes SHA256, and hydrates typed DTOs."""
    captured_events = []

    def handle_audit(event):
        captured_events.append(event)

    event_bus.subscribe("EGRESS_HTTP_AUDIT", handle_audit)
    set_trace_id("trace-uuidv7-test-999")

    # Mock Transport Handler
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Trace-ID") == "trace-uuidv7-test-999"
        return httpx.Response(
            status_code=200,
            json={
                "accountNumber": "9031842901",
                "accountName": "Enterprise SME Store",
                "status": "ACTIVE",
            },
        )

    mock_transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=mock_transport) as mock_httpx:
        client = AuditedHttpClient(client=mock_httpx)

        headers = {"Authorization": "Bearer secret_test_key_123", "X-Api-Key": "super_secret"}
        request_body = {"bvn": "22298765432", "card": "5399 4100 2938 1204", "name": "Emeka"}

        dto = await client.request(
            method="POST",
            url="https://api.moniepoint.com/v1/virtual-accounts",
            json_body=request_body,
            headers=headers,
            response_dto=SampleExpectedResponseDTO,
            target_service="MONIEPOINT_MFB",
        )

        assert isinstance(dto, SampleExpectedResponseDTO)
        assert dto.accountNumber == "9031842901"
        assert dto.accountName == "Enterprise SME Store"

        # Verify wire audit event
        assert len(captured_events) >= 1
        last_audit: EgressAuditEvent = captured_events[-1]
        assert last_audit.target_service == "MONIEPOINT_MFB"
        assert last_audit.trace_id == "trace-uuidv7-test-999"
        assert last_audit.masked_headers["Authorization"] == "[REDACTED_CREDENTIAL]"
        assert last_audit.masked_headers["X-Api-Key"] == "[REDACTED_CREDENTIAL]"
        assert "[REDACTED_BVN_5432]" in last_audit.request_body_redacted
        assert "[REDACTED_CARD_PAN_1204]" in last_audit.request_body_redacted
        assert len(last_audit.request_sha256) == 64
        assert len(last_audit.response_sha256) == 64


@pytest.mark.asyncio
async def test_egress_client_raises_typed_rate_limit_exception():
    """Verifies that HTTP 429 from Meta WhatsApp raises typed WhatsAppRateLimitedException."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=429,
            json={"error": {"message": "Rate limit exceeded", "type": "OAuthException", "code": 80007}},
        )

    mock_transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=mock_transport) as mock_httpx:
        client = AuditedHttpClient(client=mock_httpx)

        with pytest.raises(WhatsAppRateLimitedException) as exc_info:
            await client.request(
                method="POST",
                url="https://graph.facebook.com/v20.0/messages",
                json_body={"to": "+2348031234567"},
                response_dto=SampleExpectedResponseDTO,
                target_service="META_WHATSAPP_CLOUD",
            )
        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_egress_client_schema_mismatch_exception():
    """Verifies that corrupt or unexpected vendor JSON raises ProviderSchemaMismatchException."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        # Returns invalid schema missing required accountNumber
        return httpx.Response(
            status_code=200,
            json={"unexpected_field": "123"},
        )

    mock_transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=mock_transport) as mock_httpx:
        client = AuditedHttpClient(client=mock_httpx)

        with pytest.raises(ProviderSchemaMismatchException):
            await client.request(
                method="POST",
                url="https://api.moniepoint.com/v1/test",
                json_body={},
                response_dto=SampleExpectedResponseDTO,
                target_service="MONIEPOINT_MFB",
            )


def test_audited_http_client_requires_managed_httpx_instance():
    """Verifies fail-fast guard: AuditedHttpClient rejects unmanaged or None client."""
    with pytest.raises(TypeError) as exc:
        AuditedHttpClient(client=None)  # type: ignore
    assert "strictly requires an explicit, managed httpx.AsyncClient" in str(exc.value)

    with pytest.raises(TypeError):
        AuditedHttpClient(client="not_a_client")  # type: ignore


def test_adapters_require_audited_http_client_instance():
    """Verifies Meta and Moniepoint adapters strictly require AuditedHttpClient."""
    from app.adapters.whatsapp import MetaCloudWhatsAppAdapter
    with pytest.raises(TypeError) as exc_meta:
        MetaCloudWhatsAppAdapter("token", "phone_id", http_client=None)  # type: ignore
    assert "strictly requires an explicit, managed AuditedHttpClient" in str(exc_meta.value)

    with pytest.raises(TypeError) as exc_monie:
        MoniepointAdapter("key", "https://api.test", http_client=None)  # type: ignore
    assert "strictly requires an explicit, managed AuditedHttpClient" in str(exc_monie.value)


def test_lifespan_registry_fail_fast_and_resolution():
    """Verifies that get_default_audited_client raises RuntimeError if uninitialized."""
    import app.core.egress as egress_module
    from app.core.egress import get_default_audited_client, set_default_audited_client

    original = egress_module._LIFESPAN_AUDITED_CLIENT
    try:
        egress_module._LIFESPAN_AUDITED_CLIENT = None
        with pytest.raises(RuntimeError) as exc:
            get_default_audited_client()
        assert "not been initialized in application lifespan" in str(exc.value)

        # Register dummy and verify resolution
        dummy_httpx = httpx.AsyncClient()
        dummy_audited = AuditedHttpClient(client=dummy_httpx)
        set_default_audited_client(dummy_audited)
        assert get_default_audited_client() is dummy_audited
    finally:
        egress_module._LIFESPAN_AUDITED_CLIENT = original
