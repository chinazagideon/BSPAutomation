# 44. Concrete Google GenAI Integration and In-Process ONNX Classifier with Desk Handoff Fallback

## Context

Previous iterations of the 3-Stage Cascading NLU Pipeline (ADR-0024, ADR-0039) defined port interfaces (`LLMProviderPort`, `CustomClassifierPort`) backed by mock simulators (`MockLLMAdapter`, `MockCustomClassifierAdapter`). To transition the system into production-grade operation for Nigerian SMEs, we need concrete implementations that:
1. Interface directly with Google's latest Gemini models via the official `google-genai` asynchronous SDK.
2. Provide local transformer-based classification in Stage 2 via ONNX Runtime without introducing multi-gigabyte PyTorch dependencies.
3. Protect customer conversion funnels against external LLM outages, rate limits (HTTP 429), or missing local weights by guaranteeing zero service interruption.

## Decision

We decided to implement concrete production adapters with the following architectural guarantees:

1. **Google GenAI Structured Output Adapter (`GeminiFlashAdapter`)**:
   - Uses `google.genai.Client` via `client.aio.models.generate_content(...)` with `response_mime_type="application/json"` and `response_schema=ClassificationOutput`.
   - Strict adherence to `settings.GEMINI_MODEL`: if the configured model fails or is unprovisioned (404), the adapter does not silently alias, but logs an error and executes graceful desk handoff (`action="DISPATCH_AGENT_HANDOFF"`).
   - System instruction is injected with canonical intent and action boundary catalogs to constrain output schema values without brittle type narrowing.
   - Context slices are decoupled: persistent merchant grounding (`catalog_manifest`, `provider_context`) lives in `system_instruction`, while dynamic customer turn history is prepended directly to the user turn in `contents`.
   - Real token consumption is metered directly from `response.usage_metadata.total_token_count` to debit the merchant's `AIWallet`.
   - On any API failure (network timeout, rate limit, quota exhaustion, or JSON parsing error), the adapter traps the exception, logs OpenTelemetry error telemetry, bills 0 tokens, and returns an immediate graceful desk handoff (`action="DISPATCH_AGENT_HANDOFF"`).

2. **In-Process ONNX Runtime Classifier (`ONNXClassifierAdapter`)**:
   - Standard 3-file layout loaded from `models/nigerian_pidgin_intent/`: `model.onnx` (graph), `tokenizer.json` (HF fast tokenizer), and `labels.json` (integer-to-intent map).
   - Lazily loads runtime session and tokenizer on first invocation; if files or C++ runtime bindings are absent, logs a warning and transparently falls back to `MockCustomClassifierAdapter` for friction-free CI/CD and local development.
   - Dedicated single-task intent classification with softmax confidence scoring (`CUSTOM_MODEL_CONFIDENCE_THRESHOLD=0.75`).
   - Dialect detection is handled in parallel by a deterministic **Lexical Dialect Analyzer** inspecting Nigerian Pidgin and Commercial Slang markers.

3. **Execution Policy Overrides (`ExecutionPolicy`)**:
   - Exposes `policy` (`CASCADING_FALLBACK`, `DEEP_REASONING`, `FASTEST_PATH`, `LOCAL_MODEL`) in the public `NLUClassificationRequest` schema, allowing Swagger `/docs` and integration tests to exercise Stage 3 directly without altering environment configuration.

## Consequences

- **Pros**:
  - Delivers real, state-of-the-art semantic reasoning while bounding token costs.
  - Zero disruption to customers on external API degradation: failures seamlessly transition to human support agents with full conversational context.
  - Keeps container build lightweight (<150MB overhead for ONNX Runtime vs >2GB for PyTorch/CUDA).
- **Cons**:
  - Live Gemini calls introduce external network latency (~300–600ms) when escalated.
  - Requires maintaining ONNX export artifacts and vocabulary mappings alongside application code.
