# 30. Multi-Tiered Sliding-Window Rate Limiting with In-Memory Fallback

## Context

Different endpoint categories face distinct operational traffic profiles and threat models:
1. Public authentication routes (`/auth/login`) are targets for brute-force credential stuffing and password guessing.
2. WhatsApp webhook ingress routes (`/ingress/webhook/*`) receive high-burst event notifications from Meta/Termii infrastructure during high-volume commercial campaigns.
3. Merchant operational API routes (`/ledger/*`, `/reservations/*`, `/desk/*`) need fair-share tenant quota enforcement.

## Decision

We decided to implement **Multi-Tiered Sliding-Window Rate Limiting**:

1. **Category-Specific Rate Limit Buckets**:
   - **Auth Rate Bucket**: Strict IP-based limit on `/auth/login` (5 requests / minute) with exponential backoff on consecutive failures.
   - **Webhook Ingress Bucket**: High-burst allowance (500 requests / second per provider IP / verify token) with graceful queuing.
   - **Merchant Operational Bucket**: Sliding-window quota (120 requests / minute per authenticated tenant).
2. **Redis-Backed with Local In-Memory Fallback**:
   - Primary rate tracking uses Redis sorted sets (`ZADD` / `ZREMRANGEBYSCORE`) for millisecond sliding-window precision across horizontally-scaled API workers.
   - If Redis is unavailable or unconfigured (such as during local development and automated CI tests), the rate limiter automatically degrades to an in-process thread-safe in-memory sliding window cache without crashing the server.

## Consequences

- **Pros**:
  - Eliminates authentication brute-force vulnerabilities.
  - Prevents WhatsApp webhook dropouts from overly strict global rate limits.
  - Guarantees seamless offline developer workflow and unit test execution without mandatory external Redis instances.
- **Cons**:
  - Requires maintaining dual tracking adapters (Redis sorted set + in-memory LRU).
