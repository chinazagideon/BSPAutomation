# 26. Strict Cryptographic Multi-Tenant Context Resolution

## Context

In a multi-tenant SME platform operating across commerce, fintech ledgering, and customer messaging, loose tenant resolution (such as accepting unverified `X-Merchant-ID` headers, URL path parameters, or ambient dev fallbacks) presents catastrophic risks of horizontal privilege escalation and cross-tenant data leakage. If an attacker or compromised client provides a forged merchant identifier in a header or URL path, unverified resolution could mistakenly bind the PostgreSQL Row-Level Security (RLS) session variable (`SET LOCAL app.current_merchant_id = ...`) to another tenant's data.

## Decision

We decided to implement **Strict Cryptographic Multi-Tenant Context Resolution** with zero unverified fallback mechanisms:

1. **Operator & Desk Endpoints (`JWT` Channel)**:
   - Tenant context (`merchant_id`, `user_id`, `role`) is extracted exclusively from a cryptographically signed and verified JWT access token.
   - Any conflicting or unauthenticated `X-Merchant-ID` headers or path parameters are completely ignored and stripped from tenant resolution.
2. **Webhook Ingress Endpoints (`WEBHOOK` Channel)**:
   - Tenant context is resolved dynamically only after verifying the provider's cryptographic signature (e.g., Meta Cloud `X-Hub-Signature-256` HMAC validation).
   - The merchant is resolved via a verified mapping (e.g., recipient `phone_number_id` or registered business phone).
3. **B2B / Integration Endpoints (`API_KEY` Channel)**:
   - Tenant context is authenticated via high-entropy, hashed merchant API keys (`X-API-Key: bsp_live_...`) checked against constant-time database hashes.
4. **Elimination of Dev Fallback in Core Resolvers**:
   - The permissive `DEV_FALLBACK` is entirely removed from the resolver pipeline to prevent accidental activation in production or test environments. Missing credentials fail fast with `401 Unauthorized`.

## Consequences

- **Pros**:
  - Eliminates all horizontal privilege escalation attack vectors via header or path spoofing.
  - Guarantees that PostgreSQL RLS is always keyed by an authentic, verified merchant identity.
  - Enforces explicit, auditable channel boundaries across APIs, webhooks, and B2B integrations.
- **Cons**:
  - Development tests must use valid mock JWTs or test tokens rather than relying on ambient fallback variables.
