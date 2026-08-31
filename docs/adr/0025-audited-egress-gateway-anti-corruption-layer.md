# 25. Centralized Audited Egress Gateway with Typed DTO Anti-Corruption Layer (ACL)

## Context

In an enterprise conversational and financial platform integrating with third-party payment rails (Moniepoint MFB, Paystack), messaging providers (Meta Cloud API, Termii), and LLM providers (Google Gemini), allowing un-audited direct HTTP client calls (`httpx.post(...)`) creates significant security, compliance, and maintainability risks:
1. **Audit & Compliance Blind Spots**: Outbound network requests and external responses are not recorded in an immutable audit trail, violating Nigerian Data Protection Act (NDPA 2023) accountability principles and hindering payment discrepancy forensics.
2. **Credential & PII Leakage Risk**: Outgoing payloads and incoming responses might inadvertently expose API secrets, bearer tokens, or sensitive customer PII (BVN, NIN, Card PAN) in application logs.
3. **Domain Contamination & Vendor Fragility**: Without a formal Anti-Corruption Layer (ACL), domain entities and application services directly consume fragile, unstructured third-party JSON envelopes that are subject to breaking vendor changes.

## Decision

We decided to implement a **Centralized Audited Egress Gateway (`AuditedHttpClient`)** that combines **Wire-Level Ingress/Egress Auditing** with a **Typed DTO Anti-Corruption Layer (ACL)**:

1. **Transport-Level Wire Auditing & Cryptographic Integrity**:
   - Every outbound HTTP call passes through `AuditedHttpClient`.
   - Automatically masks authorization headers and API keys (`[REDACTED_CREDENTIAL]`).
   - Sanitizes sensitive Nigerian PII in request and response bodies.
   - Computes SHA-256 cryptographic hashes (`request_sha256`, `response_sha256`) of the exact wire payload for non-repudiation.
   - Emits asynchronous `EgressAuditEvent` payloads to the `EventBus` for non-blocking persistence in `compliance.egress_audit_logs`.

2. **Typed DTO Hydration & Anti-Corruption Layer (ACL)**:
   - The generic method signature `request[T](..., response_dto: Type[T]) -> T` validates and hydrates raw external JSON into strongly-typed Pydantic v2 DTOs.
   - Core bounded contexts (`ledger`, `ingress`, `reservations`, `desk`) interact exclusively with internal domain DTOs, completely insulated from external vendor schema changes.

3. **Typed Error Hydration & Domain Exceptions**:
   - HTTP 4xx/5xx responses are parsed into structured error DTOs and converted into domain-specific exceptions (`PaymentGatewayDeclinedException`, `WhatsAppRateLimitedException`, `ProviderSchemaMismatchException`) instead of generic transport errors.

4. **Distributed Trace Context Propagation**:
   - A `trace_id` generated at the ingress boundary is propagated via Python `contextvars` to every outbound HTTP call and background job, enabling 100% end-to-end trace correlation.

## Consequences

- **Pros**:
  - Full non-repudiation and compliance auditability for all external network interactions.
  - Zero domain contamination from vendor API changes.
  - Guaranteed fail-fast schema validation at the HTTP boundary.
  - Asynchronous audit event emission prevents latency penalties on the main event loop.
- **Cons**:
  - Requires maintaining explicit DTO models for each external API endpoint.
