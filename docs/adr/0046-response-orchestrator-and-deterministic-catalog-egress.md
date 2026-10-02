# 46. Response Orchestrator and Deterministic Catalog Egress Pipeline

## Context

The 3-Stage Cascading NLU Pipeline (ADR-0024) classifies incoming customer intent (e.g. `PRICE_INQUIRY`) and returns a plain text string `suggested_reply`. Previously, the background worker dispatched this string directly via WhatsApp text messages. This created critical architectural limitations:
1. **Static Responses**: Responses were hardcoded strings ungrounded in the authenticated merchant's live catalog.
2. **Suboptimal UX**: High-intent shopping queries were answered with unstructured walls of text rather than native Meta WhatsApp Interactive components (Interactive Lists, 3-Button Product Cards).
3. **Decoupled Actions**: Customers could not tap a specific product variant to view pricing details or seamlessly transition into slot-filling checkout (`NegotiationFrameManager`).

## Decision

We decided to introduce a decoupled **Response Orchestration Layer** (`ResponseOrchestrator`, `ResponseClassifier`, `ResponseFormatter`) that intercepts the pipeline between NLU classification and egress dispatch inside the asynchronous worker (`_execute_webhook_processing`).

```
[Inbound Webhook] 
       │
[PII Sanitizer] ──> [Cascading NLU Pipeline] ──> ClassificationResult
                                                       │
                                      ┌────────────────┴────────────────┐
                                      ▼                                 ▼
                         [ResponseOrchestrator]             [CatalogSearchService]
                                      │                                 │
                                      ▼                                 │
                             ResponseClassifier ◄───────────────────────┘
                                      │
                                      ▼ (ResponseStrategy)
                              ResponseFormatter
                                      │
                                      ▼
                           [EgressPayloadEnvelope]
                                      │
                         [Audited WhatsApp Egress]
                                      │
                          [Customer WhatsApp UI]
```

1. **Separation of Understanding and Action**:
   - `CentralInferenceEngine` / `CascadingNLUPipeline`: Solely responsible for semantic *understanding* (intent, lead tier, urgency, extracted entities).
   - `ResponseOrchestrator`: Responsible for *action* (retrieving catalog state, deciding message presentation, rendering channel payloads).

2. **Deterministic Response Classifier (`ResponseClassifier`)**:
   Maps `(intent, extracted_entities, catalog_results_count)` directly to a `ResponseStrategy` without calling external LLM APIs (0 token cost, <1ms):
   - `CATALOG_PRODUCT_LIST`: When inquiry matches multiple catalog items (rendered as WhatsApp Interactive List).
   - `SINGLE_PRODUCT_QUOTE`: When inquiry targets a specific item or exactly 1 match (rendered as 3-Button Product Card).
   - `CATALOG_MISS_ALERT`: When 0 matches exist for an authenticated merchant in production.
   - `FULL_CATALOG_BROWSE`: When customer asks general catalog/pricing questions without product entities.

3. **Pure Functional Response Formatter (`ResponseFormatter`)**:
   Converts domain entities and catalog offerings into a typed `EgressPayloadEnvelope` DTO:
   - For `CATALOG_PRODUCT_LIST`: Emits an Interactive List (header, body text, up to 10 rows with SKU, title, and formatted Naira price).
   - For `SINGLE_PRODUCT_QUOTE`: Emits a rich product card with up to 3 action buttons:
     1. `[Order Now]` ➔ ID: `SET_SLOT:sku:{sku}` (Binds SKU and initiates slot-filling hold)
     2. `[View Catalog]` ➔ ID: `INTENT:PRICE_INQUIRY` (Re-displays catalog list)
     3. `[Speak to Agent]` ➔ ID: `INTENT:HUMAN_AGENT_HANDOFF` (Escalates to live desk)

4. **Dual Interactive ID Scheme**:
   - `PRODUCT:{sku}`: Exploratory browsing. Tapping a list item returns the single product detail card.
   - `SET_SLOT:{param}:{val}`: Transactional binding. Tapping `[Order Now]` updates the active `NegotiationFrame` in Redis.

5. **Catalog Miss Event & Merchant Growth Loop**:
   When a search yields 0 results for an active merchant inquiry, `ResponseOrchestrator` publishes a `CatalogMissDetectedEvent` via the `EventBus`. The system alerts the merchant owner via internal ticket / notification, while returning a courteous acknowledgment to the customer without crashing or hallucinating.

## Consequences

- **Pros**:
  - High-converting native commerce: Customers browse clickable products without leaving WhatsApp.
  - Zero token burn for catalog rendering: Formatters use deterministic templates and verified merchant database records.
  - Testability: `ResponseOrchestrator` returns pure data DTOs (`EgressPayloadEnvelope`), enabling exhaustive unit testing without mocking HTTP wire transports.
- **Cons**:
  - WhatsApp Interactive Lists are restricted to a maximum of 10 items per section and 3 buttons per message.
  - Requires syncing catalog updates with Redis manifests.
