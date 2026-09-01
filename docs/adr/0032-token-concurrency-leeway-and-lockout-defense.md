# 32. Token Concurrency Leeway and Account Lockout Defense

## Context

In multi-client environments (mobile apps background-syncing while web dashboards poll simultaneously), concurrent calls to `/auth/refresh` using the same active refresh token can create race conditions that mistakenly trigger token theft detection and log legitimate users out. Furthermore, automated password guessing against SME merchant credentials necessitates defensive rate-limiting and temporary account lockout.

## Decision

We decided to implement **Token Rotation Concurrency Leeway** and an **Account Lockout Governor**:

1. **5-Second Refresh Token Leeway Window**:
   - When a refresh token is successfully exchanged, its state transitions to `consumed` and the newly issued token pair is cached in memory/Redis with a 5-second TTL.
   - Any concurrent request presenting that same consumed token within the 5-second window receives the already-issued token pair rather than triggering family revocation.
   - Any attempt to use a consumed token after the 5-second window expires is treated as an active replay attack and immediately revokes all active tokens in that `family_id`.
2. **Account Lockout Governor**:
   - `core.users` tracks `failed_login_attempts` (INTEGER) and `locked_until` (TIMESTAMPTZ).
   - Upon 5 consecutive failed password evaluations, `locked_until` is set to `clock_timestamp() + INTERVAL '15 minutes'`.
   - Subsequent login attempts during the lockout window fail immediately with HTTP 429 Too Many Requests.
   - Successful authentication resets `failed_login_attempts` to 0 and clears `locked_until`.
3. **Database-Backed Session Persistence (`core.refresh_tokens`)**:
   - All refresh token lineages are stored in `core.refresh_tokens` with columns `id (UUIDv7)`, `merchant_id (UUID)`, `user_id (UUID)`, `token_hash (VARCHAR(64))`, `family_id (UUID)`, `is_revoked (BOOLEAN)`, `expires_at (TIMESTAMPTZ)`, `created_at (TIMESTAMPTZ)`, protected by PostgreSQL RLS.

## Consequences

- **Pros**:
  - Eliminates false-positive session logouts from multi-tab browser races.
  - Hardens SME owner and manager accounts against distributed brute-force attacks.
  - Maintains durable audit trails of user token lineage and revocation states.
- **Cons**:
  - Requires atomic database or Redis locking during token rotation.
