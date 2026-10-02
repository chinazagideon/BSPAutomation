# Knowledge Base & Retrieval Context

Centralises multi-tenant business knowledge, policies, product catalogs, and semantic retrieval for conversational understanding and response generation across Nigerian SME workflows.

## Language

### Storage & Ingestion

**Knowledge Base Core**:
The centralized repository of merchant-specific business policies, FAQs, catalog manifests, and localized commercial idioms.
_Avoid_: Knowledge silo, data lake, content repository

**Knowledge Entry**:
An atomic unit of merchant truth containing verified business rules, catalog details, or operational constraints.
_Avoid_: Document row, article, FAQ item

**Manifest Compiler**:
A deterministic build engine that transforms active knowledge entries and provider states into compact, token-bounded Markdown or JSON summaries for model context injection.
_Avoid_: Cache builder, prompt packer, export script

**Tri-Modal Retrieval**:
A search architecture combining sub-millisecond phrase matching, structured memory manifests, and semantic similarity scoring to retrieve pertinent business facts.
_Avoid_: Hybrid search, multi-index lookup

### Context & Aggregation

**Context Aggregator**:
An orchestrator that gathers, sanitizes, and budgets cross-domain situational state into an integrated context envelope for language processing.
_Avoid_: Prompt builder, context stitcher, history fetcher

**Context Provider**:
A pluggable collector that resolves a specific slice of domain state (customer history, tenant identity, catalog slice, or open bookings) under multi-tenant isolation.
_Avoid_: State reader, context plugin, data fetcher

**Provider Registry**:
A centralized directory where domain context collectors register their resolution capabilities for asynchronous, timeout-bounded aggregation without circular code dependencies.
_Avoid_: Context broker, plugin manager, slice loader

**Aggregated Context**:
A normalized, privacy-redacted composite of customer conversation history, merchant operational state, and retrieved knowledge slices prepared for generation engines.
_Avoid_: Prompt payload, raw history, session dump

### Generation & Engine Dispatch

**Inference Engine**:
An agnostic runtime abstraction that routes classification, structured extraction, or open-ended dialogue requests across deterministic trigram, local machine learning, or external large language model backends.
_Avoid_: LLM wrapper, model router, AI client

**Execution Policy**:
A caller-specified execution directive balancing latency, cost, and depth of reasoning across the available inference engines.
_Avoid_: Model flag, speed setting, generation mode

**Task Priority**:
A classification assigned to generation requests (customer-facing vs internal administrative) that dictates scheduling precedence and throttling thresholds under token scarcity.
_Avoid_: Request priority, importance flag, task rank

**Fallback Factory**:
A deterministic generator registered for a structured schema type that provides a guaranteed type-safe object when models are unavailable or throttled.
_Avoid_: Default builder, heuristic generator, mock provider

**Ephemeral PII Hydration**:
The cryptographic substitution and subsequent reverse mapping of Nigerian financial and national identifiers around external LLM generation to prevent PII leakage to third-party APIs.
_Avoid_: Dynamic unmasking, token replacement, PII vaulting

**Centralized AI Wallet**:
A tenant-wide balance tracking prepaid token usage across all conversational and operational generation requests with transparent source attribution.
_Avoid_: Context token pot, AI credit limit, ingress wallet

**Three-Tier Degradation on Soft Limits**:
An operational protection mechanism maintaining three token balance thresholds (Normal Tier, Conservation Soft Cap, Hard Cap) that reserves remaining tokens exclusively for customer-facing chats during token scarcity.
_Avoid_: Token throttle, low-balance mode, credit limiter

**Local Tool Dispatcher**:
A deterministic, in-memory execution component that computes pricing math, verifies catalog constraints, and resolves product availability from context slices without invoking external LLM APIs.
_Avoid_: Tool calling agent, function broker, script executor

**Two-Headed Cascade**:
A multi-tier local inference design where a fast token classifier (Stage 2A) extracts entities and parameters for local tools, escalating to a generative model (Stage 2B/Stage 3) only when conversational ambiguity requires narrative synthesis.
_Avoid_: Dual model setup, hybrid LLM, split pipeline

**Local Tool Contract**:
A typed schema definition declaring mandatory parameters, validation bounds, and deterministic clarification prompt generators for an in-process local tool.
_Avoid_: Function signature, tool schema, API definition

**Parameter Convergence**:
The verification state where all mandatory parameters of a local tool contract are resolved, unambiguous, and validated against in-memory merchant manifests.
_Avoid_: Form completion, slot readiness

**Core Offering Contract**:
The universal schema base for any product, service, or commodity stored in the knowledge base, defining non-negotiable discovery attributes (`sku`, `title`, `price_kobo`, `currency`, `is_available`, `category`, and `offering_type`).
_Avoid_: Product model, item row, listing contract

**Vertical Schema**:
A domain-specific extension to the Core Offering Contract (e.g. `PHYSICAL_PRODUCT`, `SERVICE_APPOINTMENT`) discriminated by `offering_type` that captures industry-specific inventory and fulfillment attributes.
_Avoid_: Custom fields, subtype table, child schema

**Tiered Discovery**:
A multi-stage catalog search strategy prioritizing exact category matching, keyword token containment, and GIN trigram similarity while guaranteeing in-stock priority ranking.
_Avoid_: Hybrid search, basic filter, text lookup

**Catalog Miss Event**:
A business domain event emitted when customer intent queries products or services missing from the authenticated merchant's knowledge entries, alerting the merchant while delivering a polite customer fallback.
_Avoid_: Search failure, 404 alert, empty result log



