# 35. In-Memory and Redis Catalog and Provider Context Manifest Injection for Stage 3 LLM Escalation

## Context
Deploying an external vector database (pgvector / Qdrant) for Nigerian SME product catalogs introduces database connection pooling overhead, embedding generation latency (~200–500ms), and infrastructure maintenance complexity for catalogs that typically contain between 20 and 500 SKUs. Furthermore, merchants with active Meta Cloud WABA integrations have dynamic provider context (verified business profiles, operating hours, active Meta Commerce catalog IDs, and regional delivery policies) that must inform LLM reasoning without synchronous third-party API lookups during inference.

## Decision
We decided to maintain compact, structured Markdown/YAML manifests cached in Redis under:
1. `catalog:manifest:<merchant_id>`: Merchant product inventory, unit packaging, and prices.
2. `merchant:provider_context:<merchant_id>`: Asynchronously synchronized Meta provider data (verified business name, business hours, delivery zones, active Meta catalog ID).

During Stage 3 LLM escalation, `CascadingNLUPipeline` injects both manifests directly into the Gemini 3.7 Flash context window (~200–400 tokens total), providing instant, grounded pricing and operational business context with zero external vector or API lookup latency. Provider context updates occur asynchronously via background worker sync and webhook listeners (`MerchantProviderContextUpdatedEvent`), ensuring cache freshness without coupling request lifecycles.

## Consequences
- **Pros**: Sub-millisecond catalog and provider context retrieval; zero vector database infrastructure overhead; eliminates embedding generation API costs; strictly bounds LLM hallucination on prices and operating hours; async sync pattern keeps Meta context fresh without slowing down inference.
- **Cons**: Not suitable for hyper-scale catalogs with >10,000 SKUs without catalog tiering or category partitioning.
