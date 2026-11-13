# Enterprise WhatsApp Commercial Domain Glossary

## Intent Classification & Lifecycle

| Domain Term | Definition |
|-------------|------------|
| **`DELIVERY_TIMELINE_INQUIRY`** | Pre-purchase inquiry regarding merchant delivery coverage, estimated SLA times by zone (e.g. Lagos Mainland vs Island), interstate waybill options, or general fulfillment policies. |
| **`ORDER_STATUS_INQUIRY`** | Post-purchase transactional inquiry regarding the current fulfillment or dispatch status of an already placed order (e.g. "when is my order arriving?", "where is my rider?"). |
| **`UNRESOLVED_DISAMBIGUATION`** | Deterministic fallback strategy triggered when an utterance has sub-threshold confidence (<0.75) across all NLU stages; emits a 3-way navigation menu rather than guessing commercial intent. |
| **`INSTANT_CHECKOUT_ORDER`** | High-intent transactional workflow for placing an order, binding slots (product, quantity, delivery zone, fulfillment type), and generating an anti-ghosting payment hold. |
| **`PRICE_INQUIRY`** | Explicit request to see prices, rate cards, or catalog offerings for specific commodities or full merchant inventory. |

## Finite State Machine & Context Stack

| Domain Term | Definition |
|-------------|------------|
| **`LIFO ContextStack`** | Redis-backed Last-In-First-Out negotiation stack tracking the customer's active transactional frame, bound slots, missing slots, and temporary sub-flows. |
| **`Suspended Frame`** | An active checkout or negotiation frame temporarily put on hold while an out-of-flow atomic query (e.g. FAQ or order status) is answered. |
| **`Compound Resumption Envelope`** | A single unified WhatsApp message combining Part 1 (answer to out-of-flow inquiry) with Part 2 (cart resumption prompt and missing-slot buttons). |
| **`Frame Eviction`** | The complete clearing or popping of a frame from the context stack, strictly governed by explicit customer cancellation or TTL expiration. |
| **`NAV:* Protocol Namespace`** | Deterministic 0-token interactive callback identifiers (`NAV:BROWSE_CATALOG`, `NAV:RESUME_CART`, `NAV:TRACK_ORDER`, `NAV:AGENT_HANDOFF`) dispatched via `match/case` in the FSM. |

## Order Ledger & Fulfillment

| Domain Term | Definition |
|-------------|------------|
| **`ledger.customer_orders`** | Multi-tenant persistent record of customer orders linked to merchant identity, phone number, and fulfillment state. |
| **`Order Reference / Number`** | Secondary alphanumeric identifier (or short UUID prefix) for matching specific customer orders when multiple orders exist for a single phone number. |
| **`Fulfillment State`** | Lifecycle stage of an order (`PENDING_PAYMENT`, `PAYMENT_CONFIRMED`, `PROCESSING`, `DISPATCHED_IN_TRANSIT`, `DELIVERED`, `CANCELLED`). |
| **`NDPA Compliance Boundary`** | Strict privacy constraint prohibiting external phone intelligence directories or scraping; order lookups strictly utilize the in-session authenticated sender phone number. |
