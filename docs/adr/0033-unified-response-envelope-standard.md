# 33. Unified Response Envelope and RFC 7807 Hybrid Normalization

## Context

Multi-channel client consumers (merchant web dashboards, field mobile apps, and third-party integrations) across disparate bounded contexts require a predictable, type-safe API response structure. Inconsistent top-level JSON keys, mismatched casing conventions between Python backend models and client consumers, fragmented pagination schemas, and disparate error layouts create brittle integration contracts.

## Decision

We decided to establish the **Unified Response Envelope**, **Hybrid Problem Envelope**, and **Universal camelCase Wire Convention** across all client-facing and internal service endpoints:

1. **Declarative Enveloping via Generic Pydantic Models**:
   - `ApiResponse[T]`: Envelopes single entity payloads with `{ "success": true, "data": T, "meta": ResponseMeta }`.
   - `ApiListResponse[T]`: Envelopes collection payloads with `{ "success": true, "data": List[T], "meta": ResponseMeta }` where `meta.pagination` encapsulates the `OffsetPaginationDescriptor` (`page`, `pageSize`, `totalItems`, `totalPages`, `hasNext`, `hasPrev`).
   - Declarative use in FastAPI router signatures guarantees 100% accurate OpenAPI (`/docs`) schemas and automated client SDK typing.

2. **Hybrid RFC 7807 Problem Envelope**:
   - 4xx and 5xx responses emit a standardized payload:
     ```json
     {
       "success": false,
       "error": {
         "type": "urn:bsp:error:<code>",
         "title": "<error_title>",
         "status": <http_status_int>,
         "detail": "<human_or_diagnostic_detail>",
         "instance": "<request_path>",
         "invalidParams": []
       },
       "meta": {
         "traceId": "<uuidv7>",
         "timestamp": "<iso8601>",
         "processTimeMs": <float>
       }
     }
     ```
   - Wire HTTP status codes strictly synchronize with `error.status`.

3. **Universal camelCase Wire Serialization**:
   - All public request bodies and response envelopes use `camelCase` over the wire, enforced via Pydantic v2 `alias_generator = to_camel` and `populate_by_name = True`.

4. **Third-Party Ingress Webhook Exemption**:
   - Inbound webhook receivers (e.g. Meta Cloud API WhatsApp webhooks under `/ingress/webhooks/*`) adhere to the minimal `Webhook Fast-ACK Contract` to guarantee sub-25ms HTTP 200 responses.

## Consequences

- **Pros**:
  - Deterministic client-side discrimination using a simple boolean gate (`if (res.success) ... else handle(res.error)`).
  - Complete request correlation (`traceId`), latency accounting (`processTimeMs`), and pagination metadata unified in `meta`.
  - Type-safe OpenAPI schemas for all endpoints.
  - Seamless interoperability with standard TypeScript/JavaScript client libraries.
- **Cons**:
  - Endpoint handlers and schemas must be explicitly typed with `ApiResponse[T]` / `ApiListResponse[T]`.
