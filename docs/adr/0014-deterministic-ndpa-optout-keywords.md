# 14. Deterministic NDPA Opt-Out Keyword Interception

We decided to intercept opt-out keywords (`STOP`, `UNSUBSCRIBE`, `CANCEL`, `NO MORE`, `COMOT`) in the pre-routing fast-path, instantly revoking marketing consent in the immutable Consent Ledger.

Bypassing generative LLMs for opt-out requests eliminates interpretation latency and hallucination risks, ensuring strict compliance with NDPA 2023 regulations and Meta WhatsApp Business API quality tier policies.
