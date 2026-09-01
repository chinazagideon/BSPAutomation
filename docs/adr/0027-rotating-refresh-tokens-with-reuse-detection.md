# 27. Rotating Refresh Tokens with Automatic Family Revocation

## Context

Platform users (merchants, support managers, and desk agents) require persistent authenticated sessions across work shifts while operating over unreliable mobile data connections. However, long-lived stateless access tokens represent an unacceptable security risk if leaked, as they cannot be revoked before expiration without maintaining large distributed token blacklists. Conversely, purely stateful database sessions add I/O latency to every single sub-millisecond API request.

## Decision

We decided to implement **Short-Lived JWT Access Tokens with Database-Persisted Rotating Refresh Tokens**:

1. **Short-Lived JWT Access Tokens**:
   - Access tokens are signed JWTs (HS256/RS256) valid for 15 minutes.
   - Carry tenant claims (`merchant_id`, `user_id`, `role`, `token_family_id`).
   - Verified statelessly on incoming requests with zero database round-trips.
2. **Rotating Refresh Token Lifecycle**:
   - Refresh tokens are cryptographically secure 64-character random strings stored as SHA-256 digests in `core.refresh_tokens` with an expiration of 14 days.
   - On every `/auth/refresh` invocation, the presented refresh token is invalidated, and a new token pair (access token + new refresh token) is issued in the same token family.
3. **Replay Detection & Token Family Revocation**:
   - If a previously consumed (invalidated) refresh token is submitted for exchange, the authentication service flags a potential token compromise and immediately revokes all active refresh tokens in that entire token family, forcing all sessions for that user to re-authenticate.

## Consequences

- **Pros**:
  - Sub-millisecond stateless route authorization for high-throughput messaging workloads.
  - Limits exposure window of leaked access tokens to 15 minutes.
  - Deterministic intrusion detection and instant revocation of stolen session hierarchies.
- **Cons**:
  - Requires maintaining a persisted `core.refresh_tokens` table for tracking token families and rotation states.
