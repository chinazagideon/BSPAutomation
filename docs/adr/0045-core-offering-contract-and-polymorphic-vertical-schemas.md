# 45. Core Offering Contract and Polymorphic Vertical Schemas in Knowledge Base

## Context

In the initial implementation of the Centralized Knowledge Base (ADR-0039), catalog products were either modeled loosely as unstructured Markdown chunks or loaded from a hardcoded in-memory demonstration list (`DEFAULT_COMMODITY_CATALOG`). When customers ask transactional or discovery questions like *"how much is one bag of rice?"*, the system requires structured, deterministic catalog retrieval grounded in the authenticated merchant's actual inventory. 

Nigerian SMEs span diverse commercial operations—commodity distributors (bags of rice, cartons of sugar), appointment-based clinics/salons, and digital agencies. A monolithic single-table schema cannot accommodate retail inventory and booking slots without sparse columns or schema rot, while fragmented per-vertical tables break universal discovery and unified trigram search across `knowledge.entries`.

## Decision

We decided to establish a **Core Offering Contract** stored polymorphically inside `knowledge.entries` (where `entry_type = 'CATALOG'`), governed by typed Pydantic contracts and discriminated by an `offering_type` key:

1. **Core Offering Contract (Universal Base)**:
   Every catalog entry in `knowledge.entries` must share basic fields to enable universal discovery across all merchant verticals:
   - `sku` (string, unique per merchant)
   - `title` / `name` (string)
   - `offering_type` (string discriminator: `PHYSICAL_PRODUCT`, `SERVICE_APPOINTMENT`, `DIGITAL_GOOD`)
   - `price_kobo` (integer, minor currency precision)
   - `currency` (string, default `"NGN"`)
   - `is_available` (boolean)
   - `category` (string, normalized grouping e.g. `"rice"`, `"sugar"`, `"health"`)
   - `search_keywords` (array of strings, aliases, local slang, common misspellings)

2. **Vertical Schemas (`metadata_json`)**:
   Industry-specific properties are strongly typed and validated inside the `metadata_json` column based on `offering_type`:
   - `PHYSICAL_PRODUCT`: Adds `unit` (e.g. `"bag"`, `"carton"`), `weight`, `stock_quantity`, `min_order_qty`, `image_url`, `meta_catalog_id`.
   - `SERVICE_APPOINTMENT`: Adds `duration_minutes`, `deposit_kobo`, `resource_type`, `cancellation_notice_hours`.

3. **Tiered Discovery Search (`KnowledgeService.search_catalog_offerings`)**:
   Retrieval executes under tenant isolation (`merchant_id`) via a 3-tier cascade:
   - Tier 1: Exact match on normalized `category`.
   - Tier 2: Exact token containment in `search_keywords`.
   - Tier 3: Trigram similarity matching via PostgreSQL GIN `gin_trgm_ops` on `title` and `content`.
   - *Ordering Guarantee*: In-stock offerings (`is_available = TRUE`) are strictly prioritized, ordered by relevance similarity descending.

4. **Environment Isolation Guard**:
   In `development` and `test` environments with zero database catalog rows, the service may optionally fall back to `DEFAULT_COMMODITY_CATALOG` to keep unit test suites and offline development functional. In `production`, this fallback is strictly prohibited: empty results are treated as real catalog misses and trigger business alerts.

## Consequences

- **Pros**:
  - Universal discovery: a single search interface handles commodity goods, appointments, and services.
  - Zero schema churn: polymorphic JSONB storage avoids DDL migrations when adding new industry verticals.
  - Type-safe validation: Pydantic discriminator models reject malformed merchant entries on write.
  - Deterministic pricing: integer Kobo prices prevent floating-point rounding errors during multi-item calculations.
- **Cons**:
  - Requires maintaining Pydantic validation logic aligned with JSONB storage.
  - Indexing vertical-specific JSON attributes requires functional GIN expressions if cross-vertical filtering expands.
