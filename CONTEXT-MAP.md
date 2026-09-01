# Context Map

## Contexts

- [Core Identity & Tenant Infrastructure](./docs/contexts/core-identity/CONTEXT.md) — governs tenant boundary isolation, cryptographic identity issuance, role-based access control, and request lifecycle middleware.
- [Ingress & NLU](./docs/contexts/ingress-nlu/CONTEXT.md) — receives incoming WhatsApp webhooks, enforces <25ms 200 OK decoupling, operates the Dynamic Lead Qualification Engine, classifies Nigerian Pidgin/Slang intents, and routes leads through game-theoretic conversational funnels.
- [Checkout & Ledger](./docs/contexts/checkout-ledger/CONTEXT.md) — manages anti-ghosting shopping carts, generates dedicated dynamic virtual NUBANs (Moniepoint MFB primary), and enforces 4-leg double-entry balance verification on all settlements.
- [Reservations](./docs/contexts/reservations/CONTEXT.md) — coordinates atomic appointment slot booking with PostgreSQL `TSTZRANGE` GiST exclusion constraints and 10-minute anti-no-show holds.
- [Agent Desk](./docs/contexts/agent-desk/CONTEXT.md) — provides human agent queue routing with heartbeat offline detection (NEPA power/broadband failures) and 6-field zero-repeat context injection.
- [Compliance & Privacy](./docs/contexts/compliance/CONTEXT.md) — intercepts message streams to redact local PII (BVN, NIN, NUBAN), maintains deterministic opt-out keywords (`STOP`, `COMOT`), and records immutable NDPA 2023 consent audit trails.

## Relationships

- **Core Identity → All Bounded Contexts**: Injects authenticated `TenantContext` and sets PostgreSQL session `app.current_merchant_id` for strict Row-Level Security isolation.
- **Ingress & NLU → Checkout & Ledger**: Hot lead classification directly triggers dynamic virtual NUBAN generation and cart hold creation.
- **Ingress & NLU → Reservations**: Booking intent triggers atomic slot provisional hold.
- **Ingress & NLU → Agent Desk**: Low-confidence RAG answers or explicit handoffs dispatch a 6-field synthesized context payload to the human desk.
- **Compliance & Privacy → Ingress & NLU**: Pre-processing middleware sanitizes all inbound text before fast-path evaluation, scoring, or LLM prompting.
- **Checkout & Ledger ↔ Reservations**: Payment clearance on a slot hold transitions slot status from `HELD_PENDING_PAYMENT` to `CONFIRMED`.
- **Checkout & Ledger → Ingress & NLU**: Inbound payment settlement webhook triggers proactive receipt push to customer's WhatsApp chat.
