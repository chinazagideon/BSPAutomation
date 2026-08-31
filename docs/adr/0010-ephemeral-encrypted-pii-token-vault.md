# 10. Ephemeral Encrypted PII Token Vault

We decided to sanitize inbound PII (BVNs, NINs, NUBANs) using deterministic token placeholders and store the reversible mapping in an isolated, AES-256 encrypted vault with a 24-hour time-to-live (TTL).

This architecture guarantees compliance with the Nigeria Data Protection Act (NDPA 2023) by preventing third-party LLMs from seeing raw identity tokens, while preserving the ability of authorized human agents with role-based permissions to resolve transaction disputes within the 24-hour clearing window.
