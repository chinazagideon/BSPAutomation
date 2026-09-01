# Core Identity & Tenant Infrastructure Context

Provides multi-tenant boundary isolation, cryptographic identity management, role-based access control, and request lifecycle mediation for Nigerian SME merchants and platform operators.

## Language

**Tenant Context**:
An authenticated execution envelope identifying the active merchant organization and operating channel for all downstream domain operations.
_Avoid_: Merchant session, account context

**Channel-Specific Tenant Resolver**:
An authentication mechanism that binds tenant identity strictly to verified cryptographic credentials (JWT, webhook signature, or API key) and rejects unverified fallback headers.
_Avoid_: Multi-tenant finder, header parser, tenant switcher

**Rotating Refresh Token**:
A cryptographically hashed, single-use credential used to issue new short-lived access tokens that immediately revokes the entire token family if reused.
_Avoid_: Long-term token, persistent session, remember-me token

**Role Hierarchy Guard**:
An authorization barrier that enforces operational access levels based on operator role ranking combined with explicit checks for high-risk financial and compliance actions.
_Avoid_: Role checker, permission validator, ACL filter

**Distributed Trace Envelope**:
A request-scoped correlation identifier propagated across asynchronous execution contexts and HTTP response headers for auditability and incident investigation.
_Avoid_: Request ID, correlation tag, log tracker

**Token Transport Envelope**:
The hybrid carrier structure delivering authentication credentials across both JSON response bodies and secure, HttpOnly, SameSite browser cookies.
_Avoid_: Auth response, login payload, token wrapper

**Linear Role Hierarchy**:
An integer-ranked authorization model where operational capabilities automatically cascade downward from higher organizational tiers to subordinates.
_Avoid_: Role tree, permission ladder, user access matrix

**Sliding-Window Rate Limiter**:
An abuse prevention mechanism that tracks request frequency across continuous rolling time intervals partitioned by client IP, tenant tier, or webhook source.
_Avoid_: Request throttler, traffic cop, IP blocker

**Two-Tier Tenant Resolver Cache**:
A low-latency in-memory and Redis cache that maps external WhatsApp phone numbers and webhook identifiers to merchant tenant IDs.
_Avoid_: Tenant lookup cache, phone index, routing table

**Token Family Lineage**:
A cryptographically linked chain of single-use refresh tokens originating from a single authenticated login event.
_Avoid_: Session tree, token group, credential chain

**Rotation Concurrency Leeway Window**:
A short, bounded grace period during token exchange that re-serves the active token pair to accommodate near-simultaneous client requests without triggering family revocation.
_Avoid_: Refresh buffer, token delay, leeway window

**Account Lockout Governor**:
A defensive authentication policy that temporarily suspends credential evaluation for a user account after repeated consecutive failed login attempts.
_Avoid_: Password blocker, user freeze, lockout timer

**Unified Response Envelope**:
The deterministic top-level carrier structure (`success`, `data` or `error`, `meta`) wrapping all synchronous client and merchant API interactions across bounded contexts.
_Avoid_: Response wrapper, JSON envelope, API response format

**Hybrid Problem Envelope**:
The error transmission structure encapsulating an RFC 7807 problem details document within the unified envelope to ensure uniform client-side discrimination.
_Avoid_: Error payload, failure object, exception wrapper

**Response Telemetry Carrier**:
The metadata section (`meta`) within the unified envelope containing request correlation, latency accounting, and optional pagination descriptors.
_Avoid_: Response meta, audit header, trace block

**Offset Pagination Descriptor**:
The structured pagination contract within the telemetry carrier detailing current page, page size, total record counts, and boundary traversal booleans.
_Avoid_: Page info, pagination meta, paging block

**Webhook Fast-ACK Contract**:
The minimal, low-latency acknowledgement payload reserved exclusively for asynchronous third-party webhook receivers to preserve sub-25ms SLA.
_Avoid_: Webhook reply, 200 OK wrapper, fast ack

