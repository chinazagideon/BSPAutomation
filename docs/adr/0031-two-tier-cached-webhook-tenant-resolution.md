# 31. Two-Tier Cached Webhook Tenant Resolution

## Context

Inbound WhatsApp webhooks from Meta Cloud / Termii arrive with external telephone metadata (`phone_number_id`, `display_phone_number`) rather than internal application credentials. Resolving the corresponding merchant tenant via a synchronous SQL query (`SELECT id FROM core.merchants WHERE whatsapp_phone_number_id = :id`) on every incoming webhook event adds unnecessary database latency and connection pool pressure under high concurrent messaging loads, jeopardizing the <25ms webhook acknowledgment SLA.

## Decision

We decided to implement a **Two-Tier Cached Webhook Tenant Resolution Architecture**:

1. **Tier 1 (Process-Local In-Memory TTL Cache)**:
   - A thread-safe in-memory cache (`TTLCache`, 5-minute TTL, 10,000 entry capacity) stores mappings from `whatsapp_phone_number_id` to `merchant_id`.
   - Hits resolve tenant context in <0.05ms with zero I/O.
2. **Tier 2 (Distributed Redis Cache)**:
   - On a Tier 1 cache miss, check Redis key `tenant:phone_map:<phone_number_id>` (1-hour TTL).
3. **Database Fallback & Cache Population**:
   - On a Tier 2 cache miss, query `core.merchants` via PostgreSQL index `idx_merchants_phone_number_id`. Populate both Tier 1 and Tier 2 caches on hit, or reject with `404 Not Found` if unknown.
4. **Cache Invalidation on Merchant Update**:
   - Updates to merchant phone settings emit an invalidation signal that evicts stale entries from both cache tiers immediately.

## Consequences

- **Pros**:
  - Sub-millisecond tenant resolution for 99.9% of inbound webhook traffic.
  - Shields PostgreSQL connection pool from webhook traffic spikes.
  - Ensures reliable adherence to the <25ms webhook acknowledgment requirement.
- **Cons**:
  - Phone number configuration changes take up to 5 minutes to propagate if cache invalidation message is dropped (mitigated by explicit cache eviction on update).
