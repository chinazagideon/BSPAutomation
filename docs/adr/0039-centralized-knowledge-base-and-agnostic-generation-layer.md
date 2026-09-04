# 39. Centralized Knowledge Base Core and Agnostic Context Aggregation & Generation Layer

## Context

Conversational intelligence, context synthesis, and generation were initially implemented as an ad-hoc component inside the `ingress` context (ADR-0024, ADR-0035). Other bounded contexts—such as `agent-desk` (synthesizing 6-field escalation cards in ADR-0015), `reservations` (booking clarification), and `checkout-ledger` (pricing and payment assistance)—were forced to either duplicate pipeline logic, rely on brittle hardcoded regex heuristics, or bypass NLU entirely. Furthermore, coupling LLM provider adapters strictly to intent classification output contracts prevented reusable text generation, structured extraction, and shared prepaid AI token wallet accounting across the platform.

## Decision

We decided to implement a **Hybrid Architectural Model**:
1. **Shared Generation Runtime Kernel (`app.core.generation`)**: An agnostic inference engine abstraction exposing a unified port (`InferenceEnginePort`) supporting `classify`, `generate_text`, and `generate_structured(schema)`. Invocations are governed by an `ExecutionPolicy` enum (`FASTEST_PATH` via trigrams, `LOCAL_MODEL` via ONNX, `DEEP_REASONING` via Gemini 3.7 Flash, and `CASCADING_FALLBACK`).
2. **Dedicated Knowledge Bounded Context (`app.contexts.knowledge` & PostgreSQL schema `knowledge.*`)**: Manages tenant knowledge items, catalog entries, merchant policies, and slang dictionaries under strict Row-Level Security. It operates a **Tri-Modal Storage & Retrieval** strategy:
   - PostgreSQL `pg_trgm` GIN indexes for sub-millisecond keyword/slang fuzzy matching (0 tokens, ~2ms).
   - Redis-cached structured manifests (`knowledge:manifest:<merchant_id>:<topic>`) for compact operational and catalog grounding.
   - PostgreSQL `pgvector` (`VECTOR(768)`) embeddings for semantic retrieval across unstructured merchant documents without deploying an external vector database.
3. **Pluggable Context Aggregator (`ContextAggregator`)**: Orchestrates parallel context slice resolution across pluggable providers (`TenantContextProvider`, `CustomerSessionProvider`, `KnowledgeSliceProvider`, `DomainStateProvider`), enforcing NDPA 2023 PII sanitization via Compliance middleware before dispatching prompts to external LLMs.
4. **Centralized AI Wallet (`core.ai_wallets`)**: Consolidates prepaid token accounting into the core tenant schema with `source_context` ledger attribution (`INGRESS`, `DESK`, `RESERVATIONS`, `CHECKOUT`), executing deterministic fallback across all calling contexts when token balances are depleted.

## Consequences

- **Pros**:
  - Eliminates code duplication and replaces hardcoded heuristic regexes across the codebase with centralized intelligence.
  - Context-agnostic port enables any domain service to request structured JSON or text generation under uniform execution policies.
  - Tri-modal storage preserves sub-millisecond execution for transactional queries while unlocking deep semantic search via `pgvector` in PostgreSQL with zero external infrastructure overhead.
  - Transparent tenant-wide AI billing with granular source attribution.
- **Cons**:
  - Enabling `pgvector` in PostgreSQL requires the extension installed in the database image.
  - Cross-context dependencies require calling services to assemble context provider tokens rather than passing raw unverified text directly to models.
