# 1. Multi-Context Bounded Architecture

We decided to structure the enterprise platform into five distinct bounded contexts: Ingress & NLU, Checkout & Ledger, Reservations, Agent Desk, and Compliance & Privacy.

Financial double-entry ledgering, atomic PostgreSQL GiST calendar scheduling, and Nigerian Pidgin NLP routing have conflicting consistency and state models. Isolating them into explicit bounded contexts prevents domain contamination and enables independent scaling and testing.
