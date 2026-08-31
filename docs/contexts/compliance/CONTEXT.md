# Compliance & Privacy Context

Enforces Nigerian Data Protection Act (NDPA 2023) requirements, executes deterministic opt-out keyword interceptions, and protects customer PII before data leaves the trust boundary.

## Language

**PII Sanitizer**:
A deterministic middleware that detects and redacts Nigerian identifiers (BVN, NIN, NUBAN, card PAN) before text reaches external LLMs or logs.
_Avoid_: Text scrubber, filter

**Opt-Out Interceptor**:
A zero-LLM fast-path filter that immediately revokes marketing consent upon receiving trigger keywords (`STOP`, `UNSUBSCRIBE`, `CANCEL`, `COMOT`).
_Avoid_: Unsubscribe handler, cancellation bot

**Ephemeral Token Vault**:
An isolated, AES-256 encrypted datastore holding the mapping between redaction tokens and raw identifiers for a 24-hour retention window.
_Avoid_: Key-value store, PII cache

**Consent Ledger**:
An append-only, tamper-evident record of explicit customer opt-in/opt-out actions for WhatsApp marketing and transactional messaging.
_Avoid_: Permission table, subscriber list

**Redaction Token**:
A keyed placeholder (e.g., `[REDACTED_BVN_5432]`) substituted in place of sensitive customer data before routing to AI models.
_Avoid_: Mask, star string

**Chained Consent Ledger**:
An append-only, event-sourced audit table where each record contains a SHA-256 cryptographic digest chained to the prior entry's hash to guarantee tamper-evident proof of consent.
_Avoid_: Audit table, consent log

