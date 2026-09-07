# 43. Schema-Governed Tool Parameter Clarification and Ambiguity Resolution

## Context

In high-intent Nigerian WhatsApp commerce, customers frequently initiate purchasing with ambiguous or partially specified statements (e.g. *"I want 2 bags of sugar"* or *"Deliver to my shop"*). Previous fast-path rules prematurely committed these intents to transactional workflows—immediately allocating dynamic virtual NUBANs (Moniepoint MFB) and creating inventory reservation holds.

This premature commitment caused severe operational liabilities:
1. **Dynamic NUBAN Exhaustion**: Virtual NUBAN pools are strictly bounded and subject to mandatory 30-minute quarantine cooldowns ([ADR-0018](./0018-virtual-nuban-pool-quarantine.md)). Creating accounts on unclarified orders ties up accounts on ghost carts.
2. **Pricing & SKU Mismatches**: Generic terms (e.g. *"sugar"*) map to divergent SKUs (Dangote 50kg @ ₦84,000 vs. BUA 50kg @ ₦82,000 vs. 500g retail packs). Quoting the wrong item causes price disputes and inventory reconciliation failures.
3. **Cart Fragmentation**: Without fulfillment details (dispatch address vs warehouse pickup), orders cannot compute shipping fees or total payable amounts, breaking the four-leg double-entry ledger guarantee.

## Decision

We decided to establish **Schema-Governed Tool Parameter Clarification** and strictly gate transactional state commitments on **Parameter Convergence**:

1. **Local Tool Contract Preconditions**:
   - Every local tool (`CheckoutOrderTool`, `AppointmentBookingTool`) declares a typed schema of mandatory parameters (`required_params`), validation bounds, and fulfillment options.
   - The NLU pipeline (Fast-Path or Two-Headed Cascade) acts solely as an extractor, passing extracted slots to the target tool without making transactional assumptions.
2. **Gated Parameter Convergence & Full Parameter Invariant**:
   - The system strictly forbids generating dynamic virtual NUBANs, issuing payment accounts, or creating persistent PostgreSQL reservation holds until **Parameter Convergence** is achieved.
   - For delivery orders, `delivery_zone` is a mandatory invariant: the Virtual NUBAN is issued only once the exact total kobo amount (Merchandise + Dispatch Fee) is immutable.
3. **Deterministic Clarification Slot-Filling (Zero LLM Tokens)**:
   - When a parameter is missing or ambiguous (e.g., generic product matching multiple catalog SKUs), the tool returns a `NEEDS_CLARIFICATION` status alongside candidate options resolved directly from the merchant's in-memory `CatalogManifest`.
   - Clarifications are presented via Meta WhatsApp Interactive Quick-Reply Buttons (up to 3 buttons) or Interactive Lists (up to 10 rows), with a deterministic plain-text fallback.
4. **Unified Order & Fulfillment Contract**:
   - Commercial orders are governed by a unified `CheckoutOrderTool` that treats `fulfillment_type: Literal["EXPRESS_DELIVERY", "WAREHOUSE_PICKUP"]` as a required parameter rather than fragmenting fulfillment into disjoint tools.
5. **Ephemeral Redis Negotiation Frames**:
   - Multi-turn slot accumulation is persisted in Redis (`merchant:{m_id}:chat:{phone}:negotiation_frame`) with a 15-minute sliding TTL holding `{active_tool, bound_slots, missing_slots}`.
   - Incoming turns merge newly extracted slots into the active frame without redundant database writes or multi-turn LLM re-parsing.
6. **Frame Preservation on Topic Shifts**:
   - Ingress runs intent classification before slot filling. If the customer swerves to an FAQ, price objection, or human handoff, the system answers the inquiry while keeping the `NegotiationFrame` warm in Redis, enabling seamless checkout resumption.
7. **Universal Fast-Path Tool Delegation**:
   - Fast-Path regexes never generate virtual NUBANs directly. Even if a Turn 1 message appears fully specified, execution passes through `LocalToolDispatcher.evaluate(...)` to verify catalog existence and pricing before state commitment.
8. **WhatsApp Message Debounce Window**:
   - A 1.2-second Redis per-phone mutex/debounce buffer concatenates rapid multi-message bursts into a single inbound turn, preventing race conditions and duplicated prompts.
9. **Direct Interactive Button ID Slot Binding**:
   - WhatsApp quick-reply buttons and list items encode structured slot identifiers in their IDs (e.g. `SET_SLOT:sku:DANGOTE_50KG`). Inbound interactive webhooks bypass text parsing and commit directly into the active `NegotiationFrame` with 0ms NLP latency.
10. **Atomic Check-and-Hold at Convergence**:
    - At the instant Parameter Convergence is reached, the tool verifies physical inventory availability in PostgreSQL under row-level exclusion. If inventory is depleted during clarification, NUBAN generation is aborted, and an out-of-stock alternative prompt is emitted.
11. **Deterministic Cancellation Eviction**:
    - Inbound Nigerian Pidgin or English cancellation keywords (`cancel am`, `never mind`, `no buy again`) immediately evict the Redis `NegotiationFrame` and emit an acknowledgment. The 15-minute TTL acts as the automatic expiration boundary for dormant chats.
12. **Graceful Fresh Start Post-Expiry**:
    - Messages arriving after the 15-minute negotiation TTL has expired are evaluated as clean-slate inbound turns, preventing zombie cart resurrections or awkward context hallucinations.

## Consequences

- **Pros**:
  - Protects dynamic virtual NUBAN pools from ghost cart exhaustion.
  - Guarantees 100% pricing and ledger accuracy grounded in merchant catalog manifests.
  - Delivers zero-token, sub-10ms clarification turns using WhatsApp interactive components.
  - Direct button ID binding guarantees 100% precision with zero text parsing ambiguity.
  - Atomic stock verification prevents issuing payment accounts for sold-out inventory.
  - Accommodates non-linear conversational patterns with Frame Preservation.
  - Resolves rapid WhatsApp message bursts cleanly via debouncing.
- **Cons**:
  - Requires maintaining typed parameter schemas and catalog matcher logic for each tool.
  - Multi-turn negotiation frames require Redis availability (falls back to sliding history extraction if Redis is unreachable).
