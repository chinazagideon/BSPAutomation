# 42. Local Tool Dispatcher and Two-Headed Cascading Inference

## Context

In high-volume WhatsApp commercial dialogues for Nigerian SMEs, delegating multi-turn calculations, inventory lookups, and pricing validation to external Large Language Models (LLMs) via traditional cloud function calling introduces four severe liabilities:
1. **Compounded Latency**: A cloud function-calling cycle requires two full LLM network roundtrips (600–1500ms), violating responsive WhatsApp expectations.
2. **Token Wallet Drain**: Running repetitive arithmetic ("3 cartons @ 25,000 = ₦75,000") through external frontier models unnecessarily consumes merchant AI wallet tokens.
3. **Arithmetic & Pricing Hallucinations**: Probabilistic language models periodically hallucinate subtotals, apply wrong discounts, or misquote catalog SKUs.
4. **Offline Vulnerability**: Reliance on cloud LLMs for core commercial logic renders the merchant unable to negotiate or quote during upstream API outages.

## Decision

We decided to implement an in-process **Local Tool Dispatcher** coupled with a **Two-Headed Local Inference Cascade** (Stage 2A Token Classification + Stage 2B/3 Generative Synthesis) and a strictly deterministic **Fallback Factory** bedrock:

1. **Stage 2A Local Parameter & Entity Extraction**:
   - An in-process PyTorch transformer / token classifier (NER) extracts customer intent, dialect, item spans, counts, and budget signals with sub-20ms latency and zero token cost.
2. **In-Process Local Tool Execution**:
   - Extracted parameters are dispatched directly to registered local tools (`CatalogPriceCalculatorTool`, `InventoryAvailabilityTool`).
   - Tools evaluate against pre-warmed in-memory `KnowledgeBase` catalog manifests and tenant-isolated state without making external cloud API calls.
3. **Branching Resolution (Deterministic Fast-Reply vs. Grounded Escalation)**:
   - **Deterministic Fast-Reply**: If required parameters are fully resolved and confident, the system returns a template-grounded response or synthesized 6-Field Context Card immediately (0 tokens, <10ms).
   - **Clarification Slot-Filling**: If essential parameters are missing (e.g. quantity without SKU), the tool triggers a deterministic clarification prompt without engaging LLMs.
   - **Grounded Cloud Escalation**: If complex conversational nuance demands frontier reasoning (Stage 3 Gemini 3.7 Flash), the tool outputs (verified prices, totals, stock flags) are injected as immutable ground truth in the prompt context, strictly forbidding the LLM from performing math or database queries.
4. **Zero-PII Training Flywheel**:
   - Human desk agent adjustments are captured to retrain the local token classifier, strictly filtered through the NDPA 2023 `Zero-PII Training Pipeline` before persistence.
5. **Bedrock Deterministic Fallback**:
   - `SixFieldContextCardFallbackFactory` remains 100% deterministic (Regex + in-memory manifest parsing), guaranteeing type-safe execution if neural runtimes encounter memory or loading errors.

## Consequences

- **Pros**:
  - Eliminates 80–90% of cloud LLM calls for commercial quoting and inventory checks.
  - Guarantees 100% mathematical precision for commercial totals (Naira amounts and quantities).
  - Maintains strict NDPA 2023 data sovereignty with in-process PyTorch execution.
- **Cons**:
  - Requires maintaining typed input/output schemas and parameter validators for each local tool.
  - Initial deployment requires in-process memory allocation for the PyTorch transformer weights.
