# 34. Fast-ACK Ingress Signature Verification and Queue Decoupling

## Context
Meta Cloud API delivers incoming webhooks as unauthenticated HTTP POST requests containing an `X-Hub-Signature-256` HMAC-SHA256 header and telephone identifiers rather than JWT tokens. Parsing deeply nested Meta JSON structures, validating PII, and running NLU pipelines in the HTTP request lifecycle risks exceeding Meta's strict 200 OK delivery acknowledgment timeout, triggering duplicate webhook retries and thread starvation.

## Decision
We decided to bypass JWT authentication on `POST /ingress/webhooks/whatsapp`, validate the raw request bytes directly against `META_APP_SECRET` using `verify_meta_webhook_signature()`, resolve tenant identity using the two-tier phone cache (`resolve_merchant_from_phone()`), persist the raw unparsed payload to `ingress.webhook_events`, and immediately enqueue only `{"event_id": str(event.id), "merchant_id": str(merchant.id)}` to ARQ Redis before returning a sub-25ms 200 OK response. Invalid signatures are rejected immediately with HTTP 403 without database writes, and unrecognized phone IDs return HTTP 200 `IGNORED_UNKNOWN_TENANT` to prevent Meta retry loops.

## Consequences
- **Pros**: Guarantees adherence to sub-25ms Fast-ACK SLA; shields ingress webhooks from parsing failures and malformed payloads; isolates tenant resolution from database load via memory/Redis cache.
- **Cons**: Worker pool must handle deferred payload extraction and malformed schema error logging asynchronously.
