# 20. SHA-256 Chained Event-Sourced NDPA Consent Audit Ledger

We decided to record all NDPA opt-in and opt-out events in an append-only, event-sourced table (`compliance.consent_events`) with SHA-256 hash chaining (`hash = SHA256(prev_hash + phone + action + timestamp)`), paired with a materialized view for real-time status checks.

This architecture provides tamper-evident mathematical proof of consent compliance to the Nigeria Data Protection Commission (NDPC) while keeping fast-path keyword evaluation (<1ms) sub-millisecond through the materialized view.
