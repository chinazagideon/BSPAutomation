# 48. Unresolved Intent Disambiguation, Order Tracking, and Suspended Stack Preservation

## Status

Accepted (Finalized via Grilling Alignment)

## Context

During sandbox simulation testing, customer utterances concerning post-purchase order tracking (e.g., *"when is my order going to arrive?"*) and queries with unresolved/ambiguous intent were defaulting to product catalog lists and purchase flows (e.g., *"Rice Catalog (3 options) - Select an item below to view live pricing and place your order"*).

Investigation of the pipeline revealed four architectural root causes:
1. **Catalog Bias in Response Strategy Layer**: `ResponseOrchestrator.resolve` fell back to scanning raw messages for commodity tokens (`rice`, `sugar`, etc.) or querying the global catalog when search terms were ambiguous. If `catalog_count > 0`, `ResponseClassifier` forced `CATALOG_PRODUCT_LIST` or `SINGLE_PRODUCT_QUOTE`, even if the customer's intent had no purchasing motive.
2. **Missing Post-Purchase Domain Separation**: `DELIVERY_TIMELINE_INQUIRY` was designed solely as a pre-purchase logistics FAQ ("how many days does delivery take to Ikeja?"). The system lacked a first-class `ORDER_STATUS_INQUIRY` intent for tracking active/existing orders in `ledger.customer_orders`.
3. **Sticky LIFO Frame Resumption Bias**: When an incomplete checkout frame existed on the LIFO stack (`INSTANT_CHECKOUT_ORDER`), out-of-flow sub-flows returning `CATALOG_PRODUCT_LIST` or general inquiries would trigger sub-flow popping back into the catalog/checkout envelope.
4. **Lack of a Neutral Disambiguation Fallback**: Truly ambiguous or low-confidence queries (< 0.75 confidence) had no dedicated Meta WhatsApp Interactive envelope, causing unhandled fallbacks to leak into catalog browsing.

## Architecture Decisions (Settled)

### 1. Bifurcated Delivery & Order Tracking Taxonomy
- **`DELIVERY_TIMELINE_INQUIRY`**: Strictly pre-purchase. Handles general merchant delivery coverage, estimated SLA times by zone (e.g. Lagos Mainland vs Island), interstate waybill policies, and dispatch fees.
- **`ORDER_STATUS_INQUIRY`**: Dedicated first-class post-purchase intent. Classifies customer queries regarding an existing placed order, dispatch rider ETA, waybill tracking, and arrival time (*"when is my order going to arrive?"*, *"where is my delivery?"*, *"has my rider moved?"*).

### 2. Neutral Interactive Disambiguation Strategy (`ResponseStrategy.UNRESOLVED_DISAMBIGUATION`)
- Ambiguous and unresolved queries with confidence below threshold (< 0.75 across all NLU stages) MUST NOT show product catalogs, pricing cards, or assumed purchase flows.
- They egress an interactive 3-button Disambiguation Card using the typed `NAV:` protocol namespace:
  - **When NO cart is active on the stack**:
    1. `[Browse Catalog]` (ID: `NAV:BROWSE_CATALOG`)
    2. `[Track Existing Order]` (ID: `NAV:TRACK_ORDER`)
    3. `[Speak to Agent]` (ID: `NAV:AGENT_HANDOFF`)
  - **When an INCOMPLETE cart is suspended on the stack**:
    1. `[Resume Order]` (ID: `NAV:RESUME_CART`)
    2. `[Track Existing Order]` (ID: `NAV:TRACK_ORDER`)
    3. `[Speak to Agent]` (ID: `NAV:AGENT_HANDOFF`)
  Tapping buttons routes deterministically through `ConversationFSMService.dispatch_interactive_protocol` using Python `match/case` (0 tokens, <1ms).

### 3. Customer Order Tracking Resolution & NDPA Guard
- Primary reference: Authenticated WhatsApp sender identity (`customer_phone` from webhook context) within the tenant session (`merchant_id`). No external phone lookup tools or third-party phone directory APIs are permitted.
- Secondary reference: Alphanumeric Order Reference number / ID prefix (e.g., `#A849` or UUID string) extracted if provided by the customer.
- **Cardinality Handling**:
  - **1 Order Found**: Formats live fulfillment status, item summary, destination zone, and dispatch ETA directly.
  - **>1 Orders Found**: Renders a WhatsApp Interactive List (`ORDER_SELECT:{order_id}`) showing the 3 most recent orders with dates and summaries, allowing the user to select which order to inspect.
  - **0 Orders Found**: Informs the user that no active orders were found for their WhatsApp number, and provides an Order Reference prompt + `[Speak to Agent]` button.

### 4. Automatic Stack Resumption & Compound Egress
- When an unrelated inquiry (such as `ORDER_STATUS_INQUIRY` or a general FAQ) is answered while an incomplete checkout cart is active, the FSM preserves the suspended frame.
- The system formats a **Single Compound WhatsApp Message**:
  - **Part 1 (Top)**: Direct answer to the customer's inquiry (e.g., Order Status details or FAQ answer).
  - **Part 2 (Divider & Resumption Prompt)**:
    ```
    ━━━━━━━━━━━━━━━━━━━━
    🛒 Continuing your pending reservation for 2x Mama Gold Rice (₦156,000):
    Which area make we deliver your items to?
    ```
  - **Interactive Buttons**: Binds directly to the missing slot (e.g., `[Ikeja / Mainland]`, `[Lekki / Island]`, `[Cancel Order]`).
- Eviction policy: The suspended cart frame is evicted ONLY upon explicit customer cancellation ("cancel", "abort", "leave am") or TTL expiration.

### 5. Removal of Catalog Egress Bias
- In `ResponseOrchestrator.resolve`:
  - Blanket substring commodity scanning (matching words like "rice" or "bag" from unrelated queries) is removed.
  - Queries with empty search terms (`query_term == ""`) no longer trigger full catalog listings unless the classified intent is explicitly `SHOW_PRODUCT_CATALOG`, `BROWSE_CATALOG`, or `PRICE_INQUIRY`.
  - Non-commercial intents fall through to `UNRESOLVED_DISAMBIGUATION` or `STANDARD_TEXT`.

## Consequences

- Prevents frustrating false-positive "Buy this now" catalog interruptions when customers ask customer-support and delivery questions.
- Gives post-purchase customers instant, zero-friction tracking updates tied to their WhatsApp number.
- Preserves high-intent shopping carts without abandoning them or trapping the customer in an inescapable checkout loop.
