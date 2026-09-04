"""End-to-End Tests for OpenTelemetry & Structured Logging Pipeline across Ingress, Worker, EventBus, and Egress."""

import pytest
import json
import httpx
from uuid import uuid4
from pydantic import BaseModel
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from app.core.config import settings
from app.core.telemetry import (
    init_telemetry,
    get_tracer,
    get_active_trace_id,
    get_active_span_id,
    inject_trace_context,
    extract_trace_context,
)
from app.core.trace import set_trace_id, get_trace_id, set_context_merchant_id, get_context_merchant_id
from app.core.logging import otel_context_processor, get_logger
from app.core.events import event_bus, DomainEvent
from app.core.egress import AuditedHttpClient, EgressAuditEvent
from app.core.worker import enqueue_webhook_job, process_incoming_webhook_job


class MockResponseDTO(BaseModel):
    status: str
    message: str


@pytest.fixture(autouse=True)
def setup_otel():
    """Ensure OpenTelemetry is initialized for tests."""
    init_telemetry("bsp-test-suite")


@pytest.mark.asyncio
async def test_trace_context_extraction_and_injection():
    """Verifies W3C TraceContext injection and extraction roundtrip."""
    tracer = get_tracer("test")
    with tracer.start_as_current_span("parent_span") as span:
        active_trace = get_active_trace_id()
        active_span = get_active_span_id()
        assert len(active_trace) == 32
        assert len(active_span) == 16

        # Inject into carrier
        carrier = {}
        inject_trace_context(carrier)
        assert "traceparent" in carrier
        assert active_trace in carrier["traceparent"]

        # Extract from carrier
        extracted_ctx = extract_trace_context(carrier)
        assert extracted_ctx is not None

        # Start child span using extracted context
        with tracer.start_as_current_span("child_span", context=extracted_ctx) as child_span:
            child_trace = get_active_trace_id()
            assert child_trace == active_trace


@pytest.mark.asyncio
async def test_structlog_context_processor_binding():
    """Verifies that otel_context_processor automatically stamps logs with trace_id, span_id, and merchant_id."""
    set_context_merchant_id("merchant-test-456")
    tracer = get_tracer("test")

    with tracer.start_as_current_span("test_logging_span") as span:
        active_trace = get_active_trace_id()
        active_span = get_active_span_id()

        event_dict = {"event": "user_checkout_attempt"}
        processed = otel_context_processor(None, "info", event_dict)

        assert processed["trace_id"] == active_trace
        assert processed["span_id"] == active_span
        assert processed["merchant_id"] == "merchant-test-456"


@pytest.mark.asyncio
async def test_event_bus_publishes_with_trace_and_subscriber_spans():
    """Verifies that EventBus creates publisher and subscriber child spans and preserves causation lineage."""
    received_events = []
    subscriber_executed = False

    async def sample_handler(event: DomainEvent):
        nonlocal subscriber_executed
        subscriber_executed = True
        received_events.append(event)
        # Inside subscriber, an active span should be present
        span = trace.get_current_span()
        assert span.is_recording()

    event_bus.subscribe("telemetry.test.event", sample_handler)

    test_event = DomainEvent(
        merchant_id="merchant-999",
        event_type="telemetry.test.event",
        causation_id="cause-uuid-1234",
    )

    assert test_event.trace_id != ""
    assert test_event.causation_id == "cause-uuid-1234"

    await event_bus.publish(test_event)
    assert subscriber_executed is True
    assert len(received_events) == 1
    assert received_events[0].merchant_id == "merchant-999"
    assert received_events[0].causation_id == "cause-uuid-1234"


@pytest.mark.asyncio
async def test_egress_audited_client_w3c_injection_and_span():
    """Verifies AuditedHttpClient injects W3C traceparent headers and sets span attributes."""
    captured_traceparent = None
    captured_trace_id = None

    def mock_transport(request: httpx.Request) -> httpx.Response:
        nonlocal captured_traceparent, captured_trace_id
        captured_traceparent = request.headers.get("traceparent")
        captured_trace_id = request.headers.get("X-Trace-ID")
        return httpx.Response(200, json={"status": "OK", "message": "Dispatched"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_transport)) as mock_httpx:
        client = AuditedHttpClient(client=mock_httpx)

        tracer = get_tracer("test")
        with tracer.start_as_current_span("test_egress_caller") as caller_span:
            expected_trace_id = get_active_trace_id()

            result = await client.request(
                method="POST",
                url="https://api.whatsapp.mock/v18.0/messages",
                response_dto=MockResponseDTO,
                target_service="META_CLOUD",
                json_body={"to": "2348012345678", "type": "text"},
                merchant_id="018f6c5a-test-merchant",
            )

            assert result.status == "OK"
            assert captured_trace_id == expected_trace_id
            assert captured_traceparent is not None
            assert expected_trace_id in captured_traceparent


@pytest.mark.asyncio
async def test_ingress_http_traceparent_propagation():
    """Verifies that FastAPI Ingress middleware respects and reflects incoming W3C traceparent."""
    from app.main import app

    custom_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health", headers={"traceparent": custom_traceparent})
        assert response.status_code == 200
        assert "X-Trace-ID" in response.headers
        assert "traceparent" in response.headers
        assert response.headers["X-Trace-ID"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert response.headers["traceparent"].startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
        assert response.headers["traceparent"].endswith("-01")
