# 28. Global Observability Pipeline and RFC 7807 Error Normalization

## Context

A multi-tenant conversational and financial platform processing asynchronous WhatsApp webhooks, lead scoring, and bank transfers requires deterministic request traceability, millisecond latency accounting, and structured error responses. Unhandled exceptions or varying error response schemas between bounded contexts make client handling brittle and cloud incident forensics difficult.

## Decision

We decided to establish a **Strictly-Ordered Global Middleware Pipeline** paired with **RFC 7807 Problem Details Error Normalization**:

1. **Deterministic Pipeline Sequence**:
   - `TraceContextMiddleware`: Extracts incoming `X-Request-ID` / `X-Trace-ID` or generates a UUIDv7, binding it to Python `contextvars` for thread-safe asynchronous logging and returning it in response headers.
   - `ProcessTimeMiddleware`: Measures wall-clock execution time and appends `X-Process-Time-Ms` to response headers.
   - `GlobalExceptionMiddleware`: Catches all unhandled exceptions, maps typed domain exceptions (`DomainGatewayException`, `HTTPException`, validation errors) to standard RFC 7807 JSON schemas, and logs full trace stacks.
   - `CORSMiddleware`: Handles browser security headers.
   - `RateLimitMiddleware`: Enforces sliding-window rate limits per IP and per authenticated tenant using Redis.
2. **RFC 7807 Problem Details Schema**:
   - All 4xx and 5xx responses emit a standardized payload:
     `{"type": "urn:bsp:error:<code>", "title": "...", "status": <int>, "detail": "...", "instance": "<path>", "trace_id": "<uuid>"}`.

## Consequences

- **Pros**:
  - Unified error schema across all bounded contexts and client applications.
  - Complete end-to-end trace correlation linking ingress requests to outbound webhook jobs and database queries.
  - Enforced SLA visibility via explicit latency headers.
- **Cons**:
  - Requires maintaining central exception mapping tables in the core framework.
