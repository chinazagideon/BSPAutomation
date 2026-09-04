"""Centralized Audited Egress Gateway with Typed DTO Anti-Corruption Layer (ACL)."""

import time
import json
import re
from typing import TypeVar, Type, Optional, Dict, Any, Union
from pydantic import BaseModel, ValidationError
import httpx

from app.core.config import settings
from app.core.trace import get_trace_id, get_context_merchant_id
from app.core.security import compute_sha256_hash
from app.core.events import event_bus, DomainEvent
from app.core.telemetry import get_tracer, inject_trace_context
from app.core.logging import get_logger
from opentelemetry.trace import StatusCode, SpanKind
from app.core.exceptions import (
    DomainGatewayException,
    PaymentGatewayDeclinedException,
    PaymentGatewayTimeoutException,
    WhatsAppRateLimitedException,
    WhatsAppDeliveryFailedException,
    ProviderSchemaMismatchException,
)

logger = get_logger("egress.client")

T = TypeVar("T", bound=BaseModel)

# Sensitive header keys to mask in egress audit trails
SENSITIVE_HEADERS = {"authorization", "x-api-key", "api_key", "token", "secret", "cookie", "x-hub-signature-256"}


def mask_sensitive_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Masks secret tokens and authorization headers before logging or auditing."""
    if not headers:
        return {}
    masked: Dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADERS or "key" in k.lower() or "token" in k.lower() or "secret" in k.lower():
            masked[k] = "[REDACTED_CREDENTIAL]"
        else:
            masked[k] = v
    return masked


def sanitize_wire_payload(payload: Any) -> str:
    """Sanitizes outgoing or incoming raw wire payloads to mask financial PII."""
    if payload is None:
        return ""
    if isinstance(payload, BaseModel):
        text = payload.model_dump_json()
    elif isinstance(payload, (dict, list)):
        text = json.dumps(payload)
    else:
        text = str(payload)

    # 1. Mask 16-digit Card PANs
    text = re.sub(r"\b(?:\d{4}[-\s]?){3}\d{4}\b", lambda m: f"[REDACTED_CARD_PAN_{m.group(0)[-4:]}]", text)
    # 2. Mask 11-digit BVNs
    text = re.sub(r"\b(22\d{9})\b", lambda m: f"[REDACTED_BVN_{m.group(0)[-4:]}]", text)
    # 3. Mask 11-digit NINs
    text = re.sub(r"\b([1-9]\d{10})\b", lambda m: f"[REDACTED_NIN_{m.group(0)[-4:]}]", text)

    return text


class EgressAuditEvent(DomainEvent):
    """Event emitted for every outbound third-party API request and response cycle."""
    trace_id: str
    target_service: str
    http_method: str
    url: str
    masked_headers: Dict[str, str]
    request_body_redacted: str
    request_sha256: str
    response_status_code: int
    response_body_redacted: str
    response_sha256: str
    latency_ms: float
    is_success: bool


def create_pooled_http_client() -> httpx.AsyncClient:
    """
    Factory creating a persistent, production-grade httpx.AsyncClient connection pool.
    Enforces keep-alive limits and granular connect/read/write/pool timeouts from Settings.
    """
    limits = httpx.Limits(
        max_connections=settings.HTTP_POOL_MAX_CONNECTIONS,
        max_keepalive_connections=settings.HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=settings.HTTP_POOL_KEEPALIVE_EXPIRY_SECONDS,
    )
    timeout = httpx.Timeout(
        connect=settings.HTTP_CONNECT_TIMEOUT_SECONDS,
        read=settings.HTTP_READ_TIMEOUT_SECONDS,
        write=settings.HTTP_WRITE_TIMEOUT_SECONDS,
        pool=settings.HTTP_POOL_TIMEOUT_SECONDS,
    )
    return httpx.AsyncClient(limits=limits, timeout=timeout)


class AuditedHttpClient:
    """
    Centralized HTTP Client Transport Interceptor.
    Enforces wire-level audit logging, secret masking, SHA-256 payload digests,
    and typed DTO hydration as an Anti-Corruption Layer (ACL).
    Strictly requires a managed, pooled httpx.AsyncClient instance.
    """

    def __init__(self, client: httpx.AsyncClient, timeout: Optional[float] = None):
        if not isinstance(client, httpx.AsyncClient):
            raise TypeError("AuditedHttpClient strictly requires an explicit, managed httpx.AsyncClient instance")
        self._client = client
        self.timeout = timeout or settings.HTTP_READ_TIMEOUT_SECONDS

    async def request(
        self,
        method: str,
        url: str,
        response_dto: Type[T],
        target_service: str,
        json_body: Optional[Union[BaseModel, Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        merchant_id: Optional[str] = None,
    ) -> T:
        """
        Executes an audited outbound HTTP request:
        1. Injects active trace_id and masks auth headers
        2. Sanitizes request body & computes request_sha256
        3. Executes wire HTTP call via persistent connection pool & measures network latency
        4. Sanitizes response body & computes response_sha256
        5. Emits EgressAuditEvent to EventBus
        6. On Error (4xx/5xx): Raises typed domain exception
        7. On Success (2xx): Hydrates and returns validated response_dto
        """
        active_trace_id = get_trace_id()
        active_merchant_id = merchant_id or get_context_merchant_id() or "018f6c5a-8b1e-7230-a890-123456789abc"

        # Prepare request body
        body_dict = json_body.model_dump(exclude_none=True) if isinstance(json_body, BaseModel) else json_body
        redacted_request_str = sanitize_wire_payload(body_dict)
        request_sha256 = compute_sha256_hash(redacted_request_str)
        masked_headers = mask_sensitive_headers(headers)

        tracer = get_tracer("bsp-egress")
        with tracer.start_as_current_span(f"http.client:{target_service}", kind=SpanKind.CLIENT) as client_span:
            client_span.set_attribute("http.method", method)
            client_span.set_attribute("http.url", url)
            client_span.set_attribute("bsp.target_service", target_service)
            client_span.set_attribute("bsp.merchant_id", active_merchant_id)
            client_span.set_attribute("bsp.request_sha256", request_sha256)

            # Tiered payload capture in span (sanitized in dev/test/staging, metadata only in prod)
            if settings.ENVIRONMENT in ["development", "staging", "test"]:
                client_span.set_attribute("bsp.request_body_redacted", redacted_request_str[:1024])

            # Inject Trace Headers (W3C traceparent + legacy X-Trace-ID)
            outbound_headers = dict(headers or {})
            inject_trace_context(outbound_headers)
            outbound_headers["X-Trace-ID"] = active_trace_id

            start_time = time.perf_counter()
            raw_response_text = ""
            status_code = 500
            is_success = False

            try:
                # Exclusively execute through the managed persistent client pool
                response = await self._client.request(
                    method=method,
                    url=url,
                    json=body_dict,
                    headers=outbound_headers,
                    params=params,
                    timeout=self.timeout,
                )

                status_code = response.status_code
                raw_response_text = response.text
                is_success = 200 <= status_code < 300

            except httpx.TimeoutException as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                client_span.record_exception(exc)
                client_span.set_status(StatusCode.ERROR, "Gateway Timeout")
                await self._emit_audit(
                    merchant_id=active_merchant_id,
                    trace_id=active_trace_id,
                    target_service=target_service,
                    method=method,
                    url=url,
                    masked_headers=masked_headers,
                    request_body=redacted_request_str,
                    request_sha256=request_sha256,
                    status_code=504,
                    response_body="[GATEWAY_TIMEOUT]",
                    response_sha256=compute_sha256_hash("[GATEWAY_TIMEOUT]"),
                    latency_ms=latency_ms,
                    is_success=False,
                )
                raise PaymentGatewayTimeoutException(
                    message=f"Timeout connecting to {target_service} at {url}",
                    provider=target_service,
                    status_code=504,
                ) from exc

            except Exception as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                client_span.record_exception(exc)
                client_span.set_status(StatusCode.ERROR, str(exc))
                await self._emit_audit(
                    merchant_id=active_merchant_id,
                    trace_id=active_trace_id,
                    target_service=target_service,
                    method=method,
                    url=url,
                    masked_headers=masked_headers,
                    request_body=redacted_request_str,
                    request_sha256=request_sha256,
                    status_code=500,
                    response_body=f"[TRANSPORT_ERROR: {str(exc)}]",
                    response_sha256=compute_sha256_hash(str(exc)),
                    latency_ms=latency_ms,
                    is_success=False,
                )
                raise DomainGatewayException(
                    message=f"Transport connection failure to {target_service}: {str(exc)}",
                    provider=target_service,
                    status_code=500,
                ) from exc

            # Calculate latency and sanitize response
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            redacted_response_str = sanitize_wire_payload(raw_response_text)
            response_sha256 = compute_sha256_hash(redacted_response_str)

            client_span.set_attribute("http.status_code", status_code)
            client_span.set_attribute("bsp.response_sha256", response_sha256)
            if settings.ENVIRONMENT in ["development", "staging", "test"]:
                client_span.set_attribute("bsp.response_body_redacted", redacted_response_str[:1024])

            if not is_success:
                client_span.set_status(StatusCode.ERROR, f"HTTP {status_code}")

            # Emit Asynchronous Audit Record to EventBus
            await self._emit_audit(
                merchant_id=active_merchant_id,
                trace_id=active_trace_id,
                target_service=target_service,
                method=method,
                url=url,
                masked_headers=masked_headers,
                request_body=redacted_request_str,
                request_sha256=request_sha256,
                status_code=status_code,
                response_body=redacted_response_str,
                response_sha256=response_sha256,
                latency_ms=latency_ms,
                is_success=is_success,
            )

            # Handle 4xx / 5xx Gateway Errors -> Throw Typed Domain Exceptions
            if not is_success:
                self._handle_gateway_error(target_service, status_code, raw_response_text)

            # Parse JSON and hydrate Typed Response DTO (Anti-Corruption Layer)
            try:
                raw_json = json.loads(raw_response_text) if raw_response_text else {}
                return response_dto.model_validate(raw_json)
            except (json.JSONDecodeError, ValidationError) as err:
                raise ProviderSchemaMismatchException(
                    message=f"Response from {target_service} violated expected DTO contract {response_dto.__name__}: {str(err)}",
                    provider=target_service,
                    status_code=status_code,
                    raw_error={"raw_response": raw_response_text},
                ) from err

    async def _emit_audit(
        self,
        merchant_id: str,
        trace_id: str,
        target_service: str,
        method: str,
        url: str,
        masked_headers: Dict[str, str],
        request_body: str,
        request_sha256: str,
        status_code: int,
        response_body: str,
        response_sha256: str,
        latency_ms: float,
        is_success: bool,
    ) -> None:
        """Publishes an EgressAuditEvent to the EventBus for background auditing."""
        audit_event = EgressAuditEvent(
            merchant_id=merchant_id,
            event_type="EGRESS_HTTP_AUDIT",
            trace_id=trace_id,
            target_service=target_service,
            http_method=method,
            url=url,
            masked_headers=masked_headers,
            request_body_redacted=request_body,
            request_sha256=request_sha256,
            response_status_code=status_code,
            response_body_redacted=response_body,
            response_sha256=response_sha256,
            latency_ms=round(latency_ms, 2),
            is_success=is_success,
        )
        await event_bus.publish(audit_event)

    def _handle_gateway_error(self, provider: str, status_code: int, raw_body: str) -> None:
        """Parses error payload and raises corresponding typed domain exception."""
        error_json: Dict[str, Any] = {}
        try:
            error_json = json.loads(raw_body) if raw_body else {}
        except Exception:
            pass

        if status_code == 429:
            if "META" in provider or "WHATSAPP" in provider:
                raise WhatsAppRateLimitedException(
                    message=f"Meta WhatsApp API rate limit reached (HTTP 429)",
                    provider=provider,
                    status_code=429,
                    raw_error=error_json,
                )
            raise DomainGatewayException(
                message=f"Rate limited by {provider} (HTTP 429)",
                provider=provider,
                status_code=429,
                raw_error=error_json,
            )

        if "MONIEPOINT" in provider or "PAYMENT" in provider:
            raise PaymentGatewayDeclinedException(
                message=f"Moniepoint MFB request rejected (HTTP {status_code})",
                provider=provider,
                status_code=status_code,
                raw_error=error_json,
            )

        if "META" in provider or "WHATSAPP" in provider:
            raise WhatsAppDeliveryFailedException(
                message=f"Meta WhatsApp message delivery failed (HTTP {status_code})",
                provider=provider,
                status_code=status_code,
                raw_error=error_json,
            )

        raise DomainGatewayException(
            message=f"External gateway {provider} failed with HTTP {status_code}",
            provider=provider,
            status_code=status_code,
            raw_error=error_json,
        )


_LIFESPAN_AUDITED_CLIENT: Optional[AuditedHttpClient] = None


def set_default_audited_client(client: AuditedHttpClient) -> None:
    """Registers the active lifespan-managed AuditedHttpClient."""
    global _LIFESPAN_AUDITED_CLIENT
    _LIFESPAN_AUDITED_CLIENT = client


def get_default_audited_client() -> AuditedHttpClient:
    """
    Resolves the active lifespan-managed AuditedHttpClient.
    Fails fast if the application lifespan context has not been initialized.
    """
    global _LIFESPAN_AUDITED_CLIENT
    if _LIFESPAN_AUDITED_CLIENT is None:
        raise RuntimeError(
            "Managed AuditedHttpClient has not been initialized in application lifespan. "
            "Ensure the FastAPI lifespan or ARQ WorkerSettings.on_startup has executed."
        )
    return _LIFESPAN_AUDITED_CLIENT
