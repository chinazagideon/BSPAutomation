# 23. Python FastAPI Modular Monolith Backend Scaffold with ARQ & Multi-Tenant RLS

## Context

Following the establishment of the bounded contexts in `CONTEXT-MAP.md`, the master PostgreSQL DDL schema in `001_enterprise_schema.sql`, and ADRs 0001–0022, we required a concrete scaffolding architecture for the core backend server that enforces:
1. Sub-25ms webhook acknowledgement decoupling for WhatsApp Business Solution Providers (BSPs).
2. Strict multi-tenant Row-Level Security (RLS) via PostgreSQL's `app.current_merchant_id`.
3. Mission-critical financial double-entry accounting with Kobo-precision (`BIGINT`).
4. Dual-layer GiST range exclusion and Redis-backed 10-minute reservation holds.
5. Live desk agent NEPA heartbeat monitoring and zero-repeat context synthesis.
6. NDPA 2023 SHA-256 chained consent auditing and PII tokenization.

## Decision

We decided to scaffold the backend as a **Context-First Modular Monolith (Hexagonal / Domain-Driven Design)** using **Python FastAPI (AsyncIO)**, **SQLAlchemy 2.0 + asyncpg**, and **ARQ (Redis-backed async job queue)**, fully orchestrated via **Docker Compose**:

1. **Context Partitioning**:
   - `backend/app/contexts/core`: Tenant merchant infrastructure, user RBAC, and billing.
   - `backend/app/contexts/ingress`: WhatsApp webhook ingestion (<25ms ACK), Fast-Path Pidgin router, Lead Qualification Engine, AI token wallet.
   - `backend/app/contexts/ledger`: Anti-Ghosting carts, Virtual NUBAN pool, 4-leg double-entry ledger reconciliation.
   - `backend/app/contexts/reservations`: Atomic appointment slots, PostgreSQL GiST range locks, 10-minute anti-no-show holds.
   - `backend/app/contexts/desk`: Agent Heartbeat Monitor (NEPA power/ISP failover <60s), 6-field Context Injector.
   - `backend/app/contexts/compliance`: NDPA 2023 SHA-256 Chained Consent Ledger, Ephemeral PII Token Vault, Opt-Out Interceptor.

2. **Multi-Channel Tenant Resolver**:
   - Ingests tenant identity across JWT Bearer tokens (dashboard/desk), WhatsApp `phone_number_id` (webhooks), pre-provisioned virtual NUBAN matching (fintech webhooks), and worker job payloads.
   - Automatically executes `SET LOCAL app.current_merchant_id = :tenant_id` on every transactional database session.

3. **Asynchronous ARQ Worker Engine**:
   - Reuses the same `asyncio` event loop, SQLAlchemy connection pool, and Pydantic schemas as FastAPI.
   - Dispatches background tasks for lead scoring, Moniepoint settlement reconciliation, and the 10-minute hold countdown releaser.

4. **Port/Adapter Hexagonal Mocking Rails**:
   - Provides swappable interfaces for Moniepoint MFB (`PaymentGatewayPort`), Meta Cloud API / Termii (`WhatsAppBSPPort`), and Google Gemini 3.7 Flash (`LLMProviderPort`) with built-in offline simulation harnesses.

5. **Docker Compose Topology**:
   - 4 coordinated services: `postgres` (PostgreSQL 16 with `btree_gist`, `pg_trgm`, and auto-init schema), `redis` (Redis 7), `api` (FastAPI hot-reload on :8000), and `worker` (ARQ job worker).

## Consequences

- **Pros**:
  - Direct 1:1 alignment with `CONTEXT-MAP.md` and `001_enterprise_schema.sql`.
  - Zero impedance mismatch between async API handlers and background job workers.
  - Zero-credential local development through comprehensive mock adapters.
  - Production-grade multi-tenancy enforced at the database kernel level via RLS.
- **Cons**:
  - Requires Docker Compose environment to run the full stack locally with PostgreSQL extensions and Redis.
