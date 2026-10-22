# 47. Multi-Provider BSP Channel Abstraction and Local Sandbox Harness

## Context

Previously, inbound webhook ingestion (`POST /api/v1/ingress/webhooks/whatsapp` and `IngressService.unpack_meta_payload`) was tightly coupled to Meta Cloud API's nested JSON schema (`entry[0].changes[0].value.messages[0]`) and `X-Hub-Signature-256` HMAC verification. Meanwhile, local testing relied either on live Meta Cloud API credentials or a passive in-memory `MockWhatsAppBSPAdapter` in Python alongside a disconnected TypeScript simulation mock in `server.ts`. This prevented end-to-end local testing of the real Python FastAPI + ARQ worker pipeline, multi-turn `NegotiationFrame` slot-filling, interactive WhatsApp primitives (Lists, 3-Button Cards, Carousels, Templates, Voice Notes), and transport/protocol edge cases (burst debouncing, 24-hour customer service window expiration, webhook replay, and rate limits), while also locking the ingress boundary to a single provider.

## Decision

We decided to decouple both the inbound webhook boundary and the local testing harness through a unified **BSP Channel Adapter** architecture and a **Local BSP Sandbox**:

1. **Provider-Parameterized Webhook Ingress (`/api/v1/ingress/webhooks/{provider}`)**:
   - The ingress router accepts `{provider}` (with `whatsapp` / `meta` resolving to the active default WhatsApp BSP adapter, alongside third-party providers such as `termii`, `twilio`, `360dialog`, or `sandbox`).
   - Each `BSPChannelAdapter` encapsulates provider-specific webhook signature verification (`verify_webhook_signature`), tenant routing key extraction (`extract_phone_number_id`), and payload normalization into a canonical `NormalizedInboundEnvelope` (`text`, `interactive` button/list reply, `audio`/`voice`, `reaction`, `location`, `unsupported`, or outbound delivery `status` update).

2. **Loopback Local BSP Sandbox Across `bsp_api` and `bsp_worker`**:
   - Instead of bypassing `AuditedHttpClient` with a passive in-memory array, local testing routes outbound `WhatsAppBSPPort` calls from `bsp_worker` through `AuditedHttpClient` to the Local BSP Sandbox endpoints hosted on `bsp_api` (`/api/v1/sandbox/...`), backed by Redis state and Server-Sent Events (`GET /api/v1/sandbox/stream`).
   - This exercises the full production egress pipeline (PII scrubbing, SHA-256 payload digests, `EgressAuditEvent` emission, and HTTP 429/5xx error handling) across the real `bsp_api` and `bsp_worker` processes while streaming rich outbound envelopes and NLU/`NegotiationFrame` telemetry in real time to the React `WhatsAppPhoneSimulator`.

3. **Stateful Protocol & Fault Injection Engine**:
   - The Local BSP Sandbox enforces WhatsApp protocol constraints locally (24-hour customer service window validation requiring template messages when expired, interactive payload limits, and asynchronous `sent` -> `delivered` -> `read` / `failed` status webhooks) and exposes fault-injection controls (multi-message burst dispatch, duplicate webhook delivery, invalid HMAC signatures, clock-shifting, and HTTP 429/500 egress failures) plus runtime NLU stage controllers (`USE_FAST_PATH`, `USE_CUSTOM_MODEL`, `USE_LLM_ESCALATION`).
