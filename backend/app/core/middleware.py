"""Global Observability, RFC 7807 Error Normalization, and Tiered Rate Limiting Middleware."""

import time
import uuid
import traceback
import collections
from typing import Dict, Deque, Optional
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.trace import set_trace_id, get_trace_id, set_context_merchant_id
from app.core.exceptions import DomainGatewayException


# -----------------------------------------------------------------------------
# 1. DISTRIBUTED TRACE CONTEXT MIDDLEWARE (ADR-0028)
# -----------------------------------------------------------------------------
class TraceContextMiddleware(BaseHTTPMiddleware):
    """
    Extracts or generates an immutable distributed trace identifier (UUIDv7/UUID4),
    injects it into async contextvars, and appends it to all downstream response headers.
    """
    async def dispatch(self, request: Request, call_next):
        trace_id = (
            request.headers.get("X-Trace-ID") or
            request.headers.get("X-Request-ID") or
            str(uuid.uuid4())
        )
        set_trace_id(trace_id)

        response: Response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = trace_id
        return response


# -----------------------------------------------------------------------------
# 2. PROCESS LATENCY TIMING MIDDLEWARE (ADR-0028)
# -----------------------------------------------------------------------------
class ProcessTimeMiddleware(BaseHTTPMiddleware):
    """Measures precise request execution latency and adds 'X-Process-Time-Ms' header."""
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        response: Response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
        return response


# -----------------------------------------------------------------------------
# 3. GLOBAL RFC 7807 EXCEPTION NORMALIZATION MIDDLEWARE (ADR-0028)
# -----------------------------------------------------------------------------
class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """
    Catches all unhandled exceptions across bounded contexts and normalizes
    them into standardized RFC 7807 Problem Details JSON envelopes.
    """
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except StarletteHTTPException as exc:
            trace_id = get_trace_id()
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "type": f"urn:bsp:error:http_{exc.status_code}",
                    "title": exc.detail if isinstance(exc.detail, str) else "HTTP Exception",
                    "status": exc.status_code,
                    "detail": str(exc.detail),
                    "instance": str(request.url.path),
                    "trace_id": trace_id,
                },
                headers={"X-Trace-ID": trace_id, **(getattr(exc, "headers", None) or {})},
            )
        except DomainGatewayException as exc:
            trace_id = get_trace_id()
            status_code = exc.status_code or status.HTTP_502_BAD_GATEWAY
            return JSONResponse(
                status_code=status_code,
                content={
                    "type": f"urn:bsp:error:gateway_{exc.provider.lower()}",
                    "title": f"{exc.provider} Gateway Error",
                    "status": status_code,
                    "detail": exc.message,
                    "error_code": exc.error_code,
                    "instance": str(request.url.path),
                    "trace_id": trace_id,
                },
                headers={"X-Trace-ID": trace_id},
            )
        except Exception as exc:
            trace_id = get_trace_id()
            print(f"[ERROR] Unhandled server exception [Trace: {trace_id}]: {str(exc)}")
            traceback.print_exc()
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "type": "urn:bsp:error:internal_server_error",
                    "title": "Internal Server Error",
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "detail": "An unexpected error occurred while processing your request.",
                    "instance": str(request.url.path),
                    "trace_id": trace_id,
                },
                headers={"X-Trace-ID": trace_id},
            )


# -----------------------------------------------------------------------------
# 4. TIERED SLIDING-WINDOW RATE LIMITING MIDDLEWARE (ADR-0030)
# -----------------------------------------------------------------------------
class InMemorySlidingWindowLimiter:
    """Thread-safe in-memory sliding-window rate limiter fallback for offline dev/tests."""
    def __init__(self):
        self._buckets: Dict[str, Deque[float]] = collections.defaultdict(collections.deque)

    def is_allowed(self, key: str, max_requests: int, window_seconds: float) -> tuple[bool, int]:
        now = time.time()
        bucket = self._buckets[key]
        # Remove timestamps outside the sliding window
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()

        if len(bucket) >= max_requests:
            oldest = bucket[0]
            retry_after = int(window_seconds - (now - oldest)) + 1
            return False, max(retry_after, 1)

        bucket.append(now)
        return True, 0


_in_memory_limiter = InMemorySlidingWindowLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Enforces multi-tiered sliding-window rate limiting:
    - Auth routes: 5 req/min per IP
    - Webhook routes: 500 req/sec burst
    - Operational routes: 120 req/min per tenant/IP
    """
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Whitelist public docs and health endpoints
        if path in ["/api/health", "/docs", "/redoc", "/openapi.json", "/"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"

        # Tier 1: Auth Endpoints (Brute-Force defense)
        auth_login_path = f"{settings.auth_cookie_path}/login"
        webhook_prefix = f"{settings.API_V1_PREFIX}{settings.INGRESS_PREFIX}/webhook"

        if path.startswith(auth_login_path):
            key = f"rl:auth:{client_ip}"
            allowed, retry_after = _in_memory_limiter.is_allowed(
                key=key,
                max_requests=settings.AUTH_RATE_LIMIT_PER_MINUTE,
                window_seconds=60.0,
            )
            if not allowed:
                trace_id = get_trace_id()
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "type": "urn:bsp:error:rate_limit_exceeded",
                        "title": "Too Many Requests",
                        "status": status.HTTP_429_TOO_MANY_REQUESTS,
                        "detail": f"Rate limit exceeded on authentication. Retry in {retry_after}s.",
                        "instance": path,
                        "trace_id": trace_id,
                    },
                    headers={"Retry-After": str(retry_after), "X-Trace-ID": trace_id},
                )

        # Tier 2: Webhook Ingress (Burst allowance)
        elif path.startswith(webhook_prefix):
            key = f"rl:webhook:{client_ip}"
            allowed, retry_after = _in_memory_limiter.is_allowed(
                key=key,
                max_requests=settings.WEBHOOK_RATE_LIMIT_PER_SECOND,
                window_seconds=1.0,
            )
            if not allowed:
                trace_id = get_trace_id()
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "type": "urn:bsp:error:webhook_rate_limit_exceeded",
                        "title": "Webhook Ingress Throttled",
                        "status": status.HTTP_429_TOO_MANY_REQUESTS,
                        "detail": "High-volume webhook burst exceeded capacity. Retry shortly.",
                        "instance": path,
                        "trace_id": trace_id,
                    },
                    headers={"Retry-After": str(retry_after), "X-Trace-ID": trace_id},
                )

        # Tier 3: Standard API Routes (Fair-share per IP/Tenant)
        else:
            key = f"rl:api:{client_ip}"
            allowed, retry_after = _in_memory_limiter.is_allowed(
                key=key,
                max_requests=settings.MERCHANT_API_RATE_LIMIT_PER_MINUTE,
                window_seconds=60.0,
            )
            if not allowed:
                trace_id = get_trace_id()
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "type": "urn:bsp:error:api_rate_limit_exceeded",
                        "title": "API Rate Limit Exceeded",
                        "status": status.HTTP_429_TOO_MANY_REQUESTS,
                        "detail": f"Merchant API quota exceeded. Please slow down. Retry in {retry_after}s.",
                        "instance": path,
                        "trace_id": trace_id,
                    },
                    headers={"Retry-After": str(retry_after), "X-Trace-ID": trace_id},
                )

        return await call_next(request)
