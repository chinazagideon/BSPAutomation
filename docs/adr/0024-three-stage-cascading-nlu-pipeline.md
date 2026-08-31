# 24. Three-Stage Cascading Hybrid NLU Pipeline with Custom Model Inference & State Controllers

## Context

In high-volume WhatsApp commercial conversational flows for Nigerian SMEs, relying exclusively on third-party LLMs (such as Google Gemini 3.7 Flash) presents three challenges:
1. **Latency overhead**: External LLM generation typically takes 300–800ms, exceeding the sub-millisecond expectation for common transactional intents (e.g., greetings, catalog requests, payment confirmations).
2. **Token cost & billing drain**: Repeated calls for high-frequency dialect queries deplete the merchant's prepaid AI wallet tokens unnecessarily.
3. **Dialect specificity**: Nigerian Pidgin and localized commercial street slang require fine-grained classification that is often more accurately handled by custom-trained transformers (e.g. HuggingFace / ONNX models) tuned on local idioms.

Conversely, relying solely on deterministic keyword or regex matching fails to handle conversational ambiguity and nuanced multi-turn negotiation.

## Decision

We decided to implement a **3-Stage Cascading Hybrid NLU Pipeline** inside the `ingress` bounded context, governed by dual **Confidence Escalation Gates** and environment-driven **NLU Stage State Controllers**:

1. **Stage 1 — Deterministic Trigram Fast-Path**:
   - Matches sanitized message text against a PostgreSQL `pg_trgm` slang dictionary and regex rule engine.
   - If `confidence >= FAST_PATH_CONFIDENCE_THRESHOLD` (default `0.90`), terminates immediately (~1–5ms, 0 tokens).
2. **Stage 2 — Custom Local Classifier**:
   - If Stage 1 is below threshold and `USE_CUSTOM_MODEL=true`, routes the message to an in-process custom model adapter (`ONNXClassifierAdapter` or `TransformersClassifierAdapter`).
   - If `confidence >= CUSTOM_MODEL_CONFIDENCE_THRESHOLD` (default `0.75`), synthesizes a localized Nigerian Pidgin / Slang response from pre-approved merchant template banks (~15–35ms, 0 tokens).
3. **Stage 3 — LLM Escalation (Gemini 3.7 Flash)**:
   - If Stage 2 confidence is below threshold and `USE_LLM_ESCALATION=true`, escalates to Gemini 3.7 Flash for deep semantic synthesis, drawing down from the merchant's `ingress.ai_wallets` token balance (~380ms).
   - If `USE_LLM_ESCALATION=false` or external APIs are unreachable, gracefully falls back to structured interactive menus or human agent desk handoff without service disruption.

## Consequences

- **Pros**:
  - Achieves zero-token cost and sub-35ms response times for ~80–90% of standard commercial inquiries.
  - Highly configurable via environment state controllers (`USE_FAST_PATH`, `USE_CUSTOM_MODEL`, `USE_LLM_ESCALATION`).
  - Swappable port/adapter pattern permits testing with lightweight mock classifiers in CI/CD without downloading multi-gigabyte neural network weights.
- **Cons**:
  - Running custom ONNX/transformer models in-process requires memory allocation (~250MB–500MB) in the container.
