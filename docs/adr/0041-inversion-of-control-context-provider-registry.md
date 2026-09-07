# 41. Inversion-of-Control Context Provider Registry with Bounded Async Gathering

## Context

The centralized `ContextAggregator` requires data slices from multiple independent bounded contexts:
- `knowledge`: product catalogs, merchant policies, and FAQs.
- `desk`: agent assignment, open escalation tickets, and recent support notes.
- `reservations`: atomic appointment holds and resource availability.
- `checkout-ledger`: active cart holds and pending virtual NUBAN settlements.

Directly importing concrete service modules from each bounded context into `app.core.generation` creates bidirectional coupling, violates bounded context isolation, and introduces circular import hazards. Furthermore, an unconstrained database query in a secondary context (e.g. evaluating complex reservation constraints) could delay prompt assembly, causing customer WhatsApp messages to breach the sub-second responsiveness threshold.

## Decision

We decided to implement an **Inversion-of-Control (IoC) Provider Registry** pattern in `app.core.generation.context`:

1. **Abstract Provider Contract**:
   Define `ContextProvider(ABC)` requiring `slice_name: str` and an asynchronous method:
   `async def resolve(merchant_id: UUID, customer_phone: str, options: Dict[str, Any]) -> ContextSlice`.
2. **IoC Startup Registration**:
   Each bounded context defines and registers its own provider implementation (`KnowledgeSliceProvider`, `DeskStateProvider`, `ReservationsStateProvider`) into `ProviderRegistry` during application lifecycle startup. `app.core.generation` has zero direct imports of domain contexts.
3. **Bounded Async Gathering**:
   `ContextAggregator.aggregate(...)` gathers requested providers concurrently via `asyncio.gather` enclosed in an `asyncio.wait_for` timeout (default `35ms`).
4. **Graceful Partial Context Degradation**:
   If an individual provider times out or encounters a transient error, `ContextAggregator` logs a structured warning, discards the slow slice (or uses a Redis-cached stale fallback), and proceeds with prompt generation rather than failing the customer interaction.

## Consequences

- **Pros**:
  - Eliminates circular dependencies between the shared kernel and domain contexts.
  - Bounded 35ms timeout guarantees prompt generation is never blocked by downstream database spikes.
  - Easy to extend: new bounded contexts can expose new context slices by registering a provider without modifying the aggregator core.
- **Cons**:
  - Asynchronous timeout enforcement means generation may occasionally proceed with partial or cached context if a provider is slow.
