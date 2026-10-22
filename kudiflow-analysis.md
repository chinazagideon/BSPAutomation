# KudiFlow Enterprise — Ambitious Codebase Analysis

## Executive Summary

KudiFlow Enterprise is a **remarkably sophisticated** WhatsApp Conversational Commerce Platform for Nigerian SMEs. After exhaustively reading every source file, SQL schema, ADR, context map, adapter, worker, and test — and researching industry best practices — this analysis identifies **13 missing components**, maps the **existing orchestration architecture** against an ideal deterministic intent→response pipeline, and proposes a **Response Classifier** system that closes the gap between "intent classified" and "correct WhatsApp message type dispatched."

> [!IMPORTANT]
> Your backend (`backend/app/`) is production-grade architecture. The frontend `server.ts` is a **legacy prototype** with hardcoded values that duplicates logic already implemented properly in the Python backend. This analysis focuses on the Python backend as the canonical system.

---

## 1. Architecture Status — What Exists

```mermaid
flowchart TD
    subgraph INGRESS["Ingress & NLU Context"]
        WH["Meta Webhook\n(< 25ms ACK)"]
        PII["PII Sanitizer\n(BVN/NIN/NUBAN/PAN)"]
        FP["Fast-Path Trigram\nClassifier (Stage 1)"]
        CM["Custom ONNX Model\n(Stage 2)"]
        LLM["Gemini 3.7 Flash\nEscalation (Stage 3)"]
    end

    subgraph ORCHESTRATION["Orchestration Layer"]
        NFM["NegotiationFrameManager\n(Redis State Machine)"]
        TD["LocalToolDispatcher\n(CheckoutOrderTool)"]
        ENG["CentralInferenceEngine"]
    end

    subgraph EGRESS["Egress Gateway"]
        AHC["AuditedHttpClient\n(SHA-256 + Trace)"]
        BSP["MetaCloudWhatsAppAdapter"]
    end

    subgraph CONTEXTS["Bounded Contexts"]
        LED["Checkout & Ledger\n(Double-Entry)"]
        RES["Reservations\n(GiST Atomic Slots)"]
        DSK["Agent Desk\n(NEPA Failover)"]
        CMP["Compliance\n(NDPA 2023)"]
        KNW["Knowledge Base\n(Trigram Search)"]
    end

    WH --> PII --> FP
    FP -->|miss| CM -->|miss| LLM
    FP -->|DISPATCH_LOCAL_TOOL| TD
    TD -->|CONVERGED| LED
    TD -->|NEEDS_CLARIFICATION| NFM
    NFM -->|slot filled| TD
    ENG --> FP & CM & LLM
    LLM -->|DISPATCH_AGENT_HANDOFF| DSK
    FP -->|ATOMIC_SLOT_HOLD| RES
    BSP --> AHC
    KNW -.->|catalog manifest| ENG
```

### ✅ What's Working Well

| Component | Status | Strength |
|---|---|---|
| 3-Stage Cascading NLU Pipeline | ✅ Implemented | Fast-path → ONNX → Gemini cascade with wallet guard |
| NegotiationFrameManager | ✅ Implemented | Multi-turn stateful slot filling with Redis persistence |
| CheckoutOrderTool | ✅ Implemented | Schema-governed parameter convergence with PII sanitization |
| Audited Egress Gateway | ✅ Implemented | SHA-256 wire digests, secret masking, OpenTelemetry spans |
| WhatsApp Adapter | ✅ Implemented | Text, buttons, lists, templates, media — full Meta Cloud API |
| ARQ Background Worker | ✅ Implemented | Decoupled async webhook processing with trace propagation |
| NEPA Heartbeat Failover | ✅ Implemented | Deduplicated outage detection with Redis state machine |
| Double-Entry Ledger | ✅ Schema defined | Immutable journal with deferred balance trigger |
| PII Sanitization | ✅ Implemented | BVN, NIN, NUBAN, CARD_PAN regex with NDPA compliance |
| Multi-Tenant RLS | ✅ Schema defined | `core.current_tenant_id()` + RLS on all 20+ tables |

---

## 2. Missing Components — The 13 Gaps

### 🔴 Critical (Blocks Production)

#### Gap 1: Response Classifier / Response Type Router

**The Problem**: When the NLU classifies an intent (e.g., `PRICE_INQUIRY`), the system returns a **hardcoded text string** as `suggested_reply`. There is no component that:

1. Determines the **optimal WhatsApp message type** (text, interactive buttons, list message, product message, catalog message, template, CTA URL)
2. Formats the response payload according to that type
3. Grounds the response in the **merchant's actual catalog data** from the knowledge base

**Current behavior** ([fast_path.py#L169-L182](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/contexts/ingress/fast_path.py#L169-L182)):
```
"how much is rice?" → Static text: "₦24,500 / carton... ₦22,000 / carton..."
```

**Expected behavior**:
```
"how much is rice?" → 
  1. Catalog search on authenticated merchant's knowledge.entries
  2. Match products by category = 'rice'
  3. Format as WhatsApp Interactive List Message with clickable products
  4. Each row: product name, price, "Add to Cart" action
```

> [!CAUTION]
> This is the **single biggest gap** in the codebase. The fast-path classifier returns generic, hardcoded catalog text regardless of which merchant the customer is chatting with. In production, Merchant A sells rice and Merchant B sells electronics — they'd get the same response.

**Proposed Component**: `ResponseClassifier` + `ResponseTypeRouter`

---

#### Gap 2: Catalog Search Service

**The Problem**: The `knowledge.entries` table and `ingress.slang_dictionary` table exist in the schema but there is **no service that queries them at runtime** during intent resolution. The [`CheckoutOrderTool`](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/core/generation/tools.py#L86-L131) uses a `DEFAULT_COMMODITY_CATALOG` hardcoded in-memory list.

**What's needed**:
- `CatalogSearchService` that queries `knowledge.entries WHERE entry_type = 'CATALOG' AND merchant_id = ?`  
- Trigram similarity search using the `gin_trgm_ops` index already defined in schema
- Results formatted into WhatsApp product messages or list messages

---

#### Gap 3: Live Catalog Manifest Injection from Database

**The Problem**: [`IngressService.get_cached_catalog_manifest()`](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/core/worker.py#L387) is referenced in the worker but the implementation in `IngressService` returns a static/None value. There's no pipeline that:

1. Loads the merchant's products from `knowledge.entries`
2. Caches them in Redis (as designed in [ADR-0035](file:///Users/imac/Artwork/BSP-WhatsApp/docs/adr/0035-in-memory-redis-catalog-manifest-injection.md))
3. Invalidates on catalog updates via `MerchantProviderContextUpdatedEvent`

---

#### Gap 4: Payment Settlement Reconciliation Worker

**The Problem**: [`reconcile_payment_settlement_job()`](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/core/worker.py#L620-L627) is a **stub** — it returns `{"status": "SETTLED_BALANCED"}` without doing anything. The entire anti-ghosting ledger system (checkout carts, virtual NUBANs, journal entries) has no actual reconciliation logic.

**What's needed**:
- Match inbound Moniepoint/NIBSS settlement webhook to `ledger.virtual_nubans` by account number
- Look up associated `ledger.checkout_carts` by `cart_id`
- Apply variance tolerance from `core.merchants.variance_tolerance_kobo`
- Create `ledger.journal_entries` and balanced `ledger.journal_postings`
- Push WhatsApp receipt to customer on successful settlement
- Transition cart status: `WAITING_FOR_TRANSFER` → `PAYMENT_RECEIVED`

---

#### Gap 5: Virtual NUBAN Assignment Service

**The Problem**: The checkout flow hardcodes `Account Number: *9031842901*` in every response ([tools.py#L129](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/core/generation/tools.py#L129), [worker.py#L427](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/core/worker.py#L427)). There is no service that:

1. Queries `ledger.virtual_nubans WHERE pool_status = 'AVAILABLE'` for the merchant
2. Atomically assigns a NUBAN to the checkout cart
3. Creates a `ledger.checkout_carts` record with `hold_expires_at`
4. Starts the 10-minute anti-ghosting countdown
5. Recycles the NUBAN to `COOLDOWN_QUARANTINE` on expiry

---

### 🟡 High Priority (Blocks Full Commerce Flow)

#### Gap 6: Expired Hold Release Cron Job

[`release_expired_reservation_holds_job()`](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/core/worker.py#L630-L632) is a `pass` stub. Without this:
- Reservation slots stuck in `HELD_PENDING_PAYMENT` forever
- Virtual NUBANs never recycled to pool
- Checkout carts never transition to `EXPIRED_RELEASED`

---

#### Gap 7: Agent Ticket Assignment & Routing

The desk context has models and a synthesized context generator, but **no automatic ticket assignment logic**:
- No round-robin or least-busy agent selection
- No queue position management
- No SSE/WebSocket push to agent dashboard
- No failover from `primary_hub_id` to `failover_hub_id` when NEPA hits

---

#### Gap 8: Moniepoint Payment Adapter (Live Integration)

The [`MoniepointAdapter`](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/adapters/moniepoint.py) port is defined but the implementation is a mock. For production:
- DVA (Dedicated Virtual Account) creation API
- Settlement webhook signature verification
- Bank transfer status polling
- Refund/reversal handling

---

#### Gap 9: WhatsApp Product & Catalog Messages

The [`MetaCloudWhatsAppAdapter`](file:///Users/imac/Artwork/BSP-WhatsApp/backend/app/adapters/whatsapp.py) supports text, buttons, lists, templates, and media — but is **missing**:
- `send_product_message()` — Single Product Message (from Meta Commerce Manager catalog)
- `send_multi_product_message()` — Multi-Product Message (up to 30 items)
- `send_catalog_message()` — Full catalog browse link
- `send_flow_message()` — WhatsApp Flows for structured forms (size/color selection, address capture)

These are the **highest-converting message types** for commerce and directly relevant to the "how much is rice?" example.

---

### 🟢 Important (Completes Enterprise Readiness)

#### Gap 10: Webhook Verification Endpoint (GET)

Meta requires a `GET /webhook` verification endpoint that responds to `hub.verify_token` challenges. This exists in `server.ts` implicitly but is not in the FastAPI backend.

---

#### Gap 11: Token Wallet Consumption Recording

The `ThreeTierWalletGuard` evaluates whether LLM calls are allowed, but **never actually deducts tokens** from `core.ai_wallets` or records entries in `core.ai_token_ledger`. The `reserve_tokens()` / `release_reservation()` calls don't persist to DB.

---

#### Gap 12: Conversation Funnel Stage Progression

`ingress.conversations.funnel_stage` has 4 values (`discovery → evaluation → negotiation → checkout`) but nothing updates them. The NLU classifies intent but doesn't advance the funnel:
- `GREETING_ENGAGEMENT` → should set `discovery`
- `PRICE_INQUIRY` → should advance to `evaluation`  
- `INSTANT_CHECKOUT_ORDER` → should advance to `negotiation`
- `CONFIRM_PAYMENT` → should advance to `checkout`

---

#### Gap 13: Consent Verification Middleware

`compliance.active_consents` materialized view exists but nothing checks it before sending promotional/marketing messages. The system should verify `OPT_IN_MARKETING` status before outbound template messages.

---

## 3. Orchestration Layer — Intent→Response Pipeline

### Current Pipeline (What Exists)

```mermaid
sequenceDiagram
    participant U as Customer (WhatsApp)
    participant W as Webhook Receiver
    participant P as PII Sanitizer
    participant N as NegotiationFrameManager
    participant F as Fast-Path Classifier
    participant T as LocalToolDispatcher
    participant L as Gemini LLM
    participant E as Egress (WhatsApp)

    U->>W: "how much is one bag of rice?"
    W->>W: 200 OK (< 25ms)
    W->>P: Sanitize PII
    P->>N: Check active negotiation frame
    N-->>F: No active frame
    F->>F: Regex match "how much"
    F-->>F: Intent: PRICE_INQUIRY
    F-->>E: suggestedReply: "₦24,500 / carton..." (HARDCODED)
    E->>U: Text message with static prices
```

### Proposed Pipeline (What Should Exist)

```mermaid
sequenceDiagram
    participant U as Customer (WhatsApp)
    participant W as Webhook Receiver
    participant P as PII Sanitizer
    participant N as NegotiationFrameManager
    participant F as Fast-Path Classifier
    participant RC as Response Classifier
    participant CS as Catalog Search
    participant RF as Response Formatter
    participant E as Egress (WhatsApp)

    U->>W: "how much is one bag of rice?"
    W->>W: 200 OK (< 25ms)
    W->>P: Sanitize PII
    P->>N: Check active negotiation frame
    N-->>F: No active frame
    F->>F: Regex match "how much" + entity: product=rice
    F-->>RC: Intent: PRICE_INQUIRY, entities: {product: rice}
    
    RC->>RC: Map intent → response strategy
    Note over RC: PRICE_INQUIRY + product entity<br/>→ CATALOG_PRODUCT_LIST
    
    RC->>CS: Search merchant catalog for "rice"
    CS->>CS: SELECT * FROM knowledge.entries<br/>WHERE entry_type='CATALOG'<br/>AND content %> 'rice'<br/>AND merchant_id = ?
    CS-->>RC: [{Mama Gold 50kg: ₦78k}, {Ofada Rice 25kg: ₦45k}, ...]
    
    RC->>RF: Format as WhatsApp Interactive List
    RF-->>E: Interactive List Message with sections
    E->>U: 📋 Clickable product list with prices
    
    Note over U: Customer taps "Mama Gold 50kg"
    U->>W: Interactive reply: "PRODUCT:RICE_MAMA_GOLD_50KG"
    W->>N: Create NegotiationFrame(intent=CHECKOUT, sku=RICE_MAMA_GOLD_50KG)
    N->>E: "How many bags? [1] [2] [5]"
```

---

## 4. Response Classifier — Proposed Architecture

The Response Classifier is the **missing bridge** between intent classification and message dispatch. It answers: *"Given this intent and these entities, what is the optimal WhatsApp response format?"*

### 4.1 Intent → Response Type Mapping (Deterministic)

| Classified Intent | Extracted Entities | Response Strategy | WhatsApp Message Type |
|---|---|---|---|
| `PRICE_INQUIRY` | `{product: "rice"}` | `CATALOG_PRODUCT_LIST` | Interactive List (up to 10 products) |
| `PRICE_INQUIRY` | `{product: "rice", quantity: "5 bags"}` | `SINGLE_PRODUCT_QUOTE` | Interactive Buttons: [Add to Cart] [View More] |
| `PRICE_INQUIRY` | `{}` (no product) | `FULL_CATALOG_BROWSE` | Catalog Message or CTA URL button |
| `INSTANT_CHECKOUT_ORDER` | `{product, quantity, location}` | `CHECKOUT_CONVERGED` | Text with NUBAN + receipt format |
| `INSTANT_CHECKOUT_ORDER` | `{product}` (missing qty) | `SLOT_CLARIFICATION` | Interactive Buttons: [1 bag] [2 bags] [5 bags] |
| `CONFIRM_PAYMENT` | `{}` | `PAYMENT_ACKNOWLEDGEMENT` | Text + pending verification animation |
| `RESERVE_APPOINTMENT` | `{date, time}` | `SLOT_CONFIRMATION` | Interactive Buttons: [Confirm ₦5k Deposit] [Change Time] |
| `RESERVE_APPOINTMENT` | `{}` | `AVAILABLE_SLOTS` | Interactive List (available time slots) |
| `HUMAN_AGENT_HANDOFF` | `{}` | `HANDOFF_CONFIRMATION` | Text with queue position + ETA |
| `GREETING_ENGAGEMENT` | `{}` | `WELCOME_MENU` | Interactive List (main service categories) |
| `DELIVERY_TIMELINE_INQUIRY` | `{order_ref}` | `ORDER_TRACKING` | Text with status + rider contact |
| `TRUST_VERIFICATION_PROOF` | `{}` | `SOCIAL_PROOF` | Media (photo of shop) + Text (reviews) |

### 4.2 Proposed Component: `ResponseClassifier`

```python
# backend/app/core/generation/response_classifier.py

class ResponseStrategy(str, Enum):
    CATALOG_PRODUCT_LIST = "CATALOG_PRODUCT_LIST"
    SINGLE_PRODUCT_QUOTE = "SINGLE_PRODUCT_QUOTE"
    FULL_CATALOG_BROWSE = "FULL_CATALOG_BROWSE"
    CHECKOUT_CONVERGED = "CHECKOUT_CONVERGED"
    SLOT_CLARIFICATION = "SLOT_CLARIFICATION"
    PAYMENT_ACKNOWLEDGEMENT = "PAYMENT_ACKNOWLEDGEMENT"
    AVAILABLE_SLOTS = "AVAILABLE_SLOTS"
    SLOT_CONFIRMATION = "SLOT_CONFIRMATION"
    HANDOFF_CONFIRMATION = "HANDOFF_CONFIRMATION"
    WELCOME_MENU = "WELCOME_MENU"
    ORDER_TRACKING = "ORDER_TRACKING"
    SOCIAL_PROOF = "SOCIAL_PROOF"
    PLAIN_TEXT = "PLAIN_TEXT"


class ResponseClassifier:
    """
    Deterministic mapper from (intent, entities) → ResponseStrategy.
    Zero LLM tokens — pure rule evaluation with entity presence checks.
    """
    
    STRATEGY_RULES: List[Tuple[str, Callable, ResponseStrategy]] = [
        ("PRICE_INQUIRY", lambda e: "product" in e and "quantity" in e, ResponseStrategy.SINGLE_PRODUCT_QUOTE),
        ("PRICE_INQUIRY", lambda e: "product" in e, ResponseStrategy.CATALOG_PRODUCT_LIST),
        ("PRICE_INQUIRY", lambda e: True, ResponseStrategy.FULL_CATALOG_BROWSE),
        ("INSTANT_CHECKOUT_ORDER", lambda e: all(k in e for k in ["sku", "quantity", "fulfillment_type"]), ResponseStrategy.CHECKOUT_CONVERGED),
        ("INSTANT_CHECKOUT_ORDER", lambda e: True, ResponseStrategy.SLOT_CLARIFICATION),
        ("CONFIRM_PAYMENT", lambda e: True, ResponseStrategy.PAYMENT_ACKNOWLEDGEMENT),
        ("RESERVE_APPOINTMENT", lambda e: "date" in e or "time" in e, ResponseStrategy.SLOT_CONFIRMATION),
        ("RESERVE_APPOINTMENT", lambda e: True, ResponseStrategy.AVAILABLE_SLOTS),
        ("HUMAN_AGENT_HANDOFF", lambda e: True, ResponseStrategy.HANDOFF_CONFIRMATION),
        ("GREETING_ENGAGEMENT", lambda e: True, ResponseStrategy.WELCOME_MENU),
    ]
    
    @classmethod
    def classify(cls, intent: str, entities: Dict[str, Any]) -> ResponseStrategy:
        for rule_intent, predicate, strategy in cls.STRATEGY_RULES:
            if intent == rule_intent and predicate(entities):
                return strategy
        return ResponseStrategy.PLAIN_TEXT
```

### 4.3 Proposed Component: `ResponseFormatter`

```python
# backend/app/core/generation/response_formatter.py

class ResponseFormatter:
    """
    Converts (ResponseStrategy, catalog_results, entities) → WhatsApp egress payload.
    Selects the optimal Meta Cloud API message type and formats the payload.
    """
    
    async def format(
        self,
        strategy: ResponseStrategy,
        catalog_results: List[Dict],
        entities: Dict[str, Any],
        merchant_context: Dict[str, Any],
    ) -> EgressPayload:
        
        match strategy:
            case ResponseStrategy.CATALOG_PRODUCT_LIST:
                return self._format_interactive_list(catalog_results, entities)
            case ResponseStrategy.SINGLE_PRODUCT_QUOTE:
                return self._format_product_quote(catalog_results[0], entities)
            case ResponseStrategy.WELCOME_MENU:
                return self._format_welcome_menu(merchant_context)
            case ResponseStrategy.FULL_CATALOG_BROWSE:
                return self._format_catalog_cta(merchant_context)
            # ... etc
    
    def _format_interactive_list(self, products: List[Dict], entities: Dict) -> EgressPayload:
        """Formats WhatsApp Interactive List Message with product sections."""
        sections = [{
            "title": "Available Products",
            "rows": [
                {
                    "id": f"PRODUCT:{p['sku']}",
                    "title": p["name"][:24],
                    "description": f"₦{p['price_naira']:,} / {p['unit']}"
                }
                for p in products[:10]
            ]
        }]
        return EgressPayload(
            message_type="interactive_list",
            header_text=f"🛒 {entities.get('product', 'Products').title()} Catalog",
            body_text=f"We found {len(products)} matching products. Tap one to order:",
            button_title="View Products",
            sections=sections,
        )
```

### 4.4 End-to-End Example: "How much is one bag of rice?"

```mermaid
flowchart TD
    A["Customer: 'How much is one bag of rice?'"] --> B["PII Sanitizer: Clean"]
    B --> C["Fast-Path: PRICE_INQUIRY<br/>entities: {product: rice, quantity: 1 bag}"]
    C --> D["ResponseClassifier.classify()<br/>→ SINGLE_PRODUCT_QUOTE"]
    D --> E["CatalogSearchService.search()<br/>merchant_id + 'rice'"]
    E --> F{"Results count?"}
    F -->|"1 match"| G["ResponseFormatter:<br/>Single product card<br/>+ [Add to Cart] button"]
    F -->|"3 matches"| H["ResponseFormatter:<br/>Interactive List<br/>with 3 rice products"]
    F -->|"0 matches"| I["ResponseFormatter:<br/>'Sorry, no rice in catalog.<br/>View full catalog?'"]
    
    G --> J["WhatsApp Egress"]
    H --> J
    I --> J
    
    J --> K["Customer sees clickable<br/>product with price + action"]
```

---

## 5. Implementation Priority Roadmap

```mermaid
flowchart LR
    subgraph P1["Phase 1: Core Commerce (2 weeks)"]
        G2["Gap 2: CatalogSearchService"]
        G3["Gap 3: Redis Catalog Cache"]
        G1["Gap 1: ResponseClassifier\n+ ResponseFormatter"]
        G5["Gap 5: NUBAN Assignment"]
    end

    subgraph P2["Phase 2: Money Flow (2 weeks)"]
        G4["Gap 4: Payment Reconciliation"]
        G6["Gap 6: Hold Expiry Cron"]
        G8["Gap 8: Moniepoint Live"]
        G11["Gap 11: Token Wallet DB"]
    end

    subgraph P3["Phase 3: Operations (1 week)"]
        G7["Gap 7: Agent Routing"]
        G9["Gap 9: Product Messages"]
        G10["Gap 10: Webhook Verify"]
        G12["Gap 12: Funnel Stages"]
        G13["Gap 13: Consent Check"]
    end

    P1 --> P2 --> P3
```

### Phase 1 Implementation Order:
1. **CatalogSearchService** — Query `knowledge.entries` with trigram similarity
2. **Redis Catalog Manifest** — Cache merchant catalogs per ADR-0035
3. **ResponseClassifier** — Deterministic intent+entity → strategy mapping
4. **ResponseFormatter** — Strategy → WhatsApp message type formatting
5. **Wire into Worker** — Insert between NLU result and egress dispatch
6. **NUBAN Assignment** — Dynamic virtual account allocation from pool

---

## 6. Legacy `server.ts` Consolidation

> [!WARNING]
> The root [`server.ts`](file:///Users/imac/Artwork/BSP-WhatsApp/server.ts) is a **prototype duplicate** of the Python backend. It has:
> - Hardcoded stats values (line 40-48)
> - In-memory state instead of PostgreSQL
> - Duplicated PII sanitization logic
> - Duplicated fast-path classifier with different behavior
> - No multi-tenancy, no RLS, no catalog integration
> 
> **Recommendation**: Keep `server.ts` only as a demo/simulator frontend server. All production logic should live in the Python backend.

---

## 7. Summary Scorecard

| Dimension | Score | Notes |
|---|---|---|
| **Schema Design** | ⭐⭐⭐⭐⭐ | Enterprise-grade. UUIDv7, RLS, GiST, kobo precision, immutable ledger. |
| **NLU Pipeline** | ⭐⭐⭐⭐ | 3-stage cascade is excellent. Missing catalog grounding. |
| **Orchestration** | ⭐⭐⭐⭐ | NegotiationFrameManager + Tool Dispatcher is strong. Missing Response Classifier. |
| **Egress Layer** | ⭐⭐⭐⭐ | Audited, traced, typed ACL. Missing product/catalog message types. |
| **Money Flow** | ⭐⭐ | Schema ready, workers are stubs. No live payment reconciliation. |
| **Agent Desk** | ⭐⭐⭐ | Context synthesis works. No routing/assignment. |
| **Compliance** | ⭐⭐⭐⭐ | PII sanitization + consent chain excellent. Missing verification middleware. |
| **Testing** | ⭐⭐⭐⭐ | 14 test files covering all contexts. Good coverage. |
| **ADR Documentation** | ⭐⭐⭐⭐⭐ | 44 ADRs. Exceptional architectural documentation. |

**Overall**: Your architecture is **top 5% for a Nigerian fintech startup**. The schema, DDD boundaries, and NLU pipeline are production-grade. The critical gap is the **Response Classifier** — the bridge between "we know what the customer wants" and "we send the right WhatsApp message format with real merchant data."
