# Workspace Engineering Rules

## Backend Architecture (`backend/`)

- **Single Responsibility Modules**: Give each class and module one responsibility. Place each external provider adapter in its own module (e.g. `app/adapters/providers/meta.py`, `termii.py`, `twilio.py`, `dialog360.py`) and keep DTO schemas in dedicated schema files.
- **Thin Routers, Dedicated Services**: Keep FastAPI `router.py` files strictly to HTTP request/response handling. Delegate orchestration, seeding, webhook synthesis, and state mutations to a dedicated service class (`service.py`).
- **Registry-Driven Provider Resolution**: Resolve adapters and strategies via a declarative registry map (`PROVIDER_REGISTRY: dict[str, Callable]`) rather than `if/elif` chains on provider strings.
- **Sandbox Isolation**: Isolate all local simulation and fault-injection adapters inside `app/sandbox/`. Production adapters in `app/adapters/` must remain free of sandbox state dependencies.
- **Vendor-Neutral Domain Naming**: Use provider-agnostic names in domain services and workers (`unpack_inbound_payload`, `inbound_envelope`, `verify_webhook_signature`) rather than vendor-specific terms (`meta`).
- **Declarative Boundary Validation (`Annotated` & `model_validate_json`)**: Push JSON parsing, PII sanitization, numeric clamping, and enum coercion into reusable Pydantic `Annotated` types (`BeforeValidator` / `AfterValidator`) and `@field_validator` hooks rather than imperative `try/except` normalization blocks in services or adapters.
- **Self-Healing Financial Invariants (`@model_validator(mode="after")`)**: Enforce Kobo/Naira numeric integrity directly on output DTOs using `@model_validator(mode="after")` so any LLM translation that drops or alters a verified currency figure automatically heals to the deterministic fallback string at the schema boundary.
- **Rich Domain Models, Thin Repositories**: Encapsulate collection invariants (LIFO stack push/pop/peek, lazy TTL pruning via `@field_validator`, depth capping, deduplication, and `@computed_field` projections) inside Pydantic domain models (`ContextStack`), keeping Redis/DB managers as thin persistence repositories.
- **Single-Source LLM Grammar Schemas (`model_json_schema()`)**: Define canonical intent/slot `Literal` types once on Pydantic DTOs and pass `Model.model_json_schema()` directly into LLM `response_format` grammar constraints rather than maintaining duplicate hand-written schema descriptions in system prompts.
- **Discriminated Unions & `match/case` Protocol Dispatch**: Parse structured callback identifiers (`SET_SLOT:*`, `PRODUCT:*`) into Pydantic Discriminated Unions (`Field(discriminator=...)`) via `@model_validator(mode="before")` and dispatch them using Python `match/case` structural pattern matching rather than `.startswith()` / `.split()` chains.

## Frontend Architecture (`src/`)

- **Composable SRP Components**: Keep React components focused on a single visual responsibility. Extract sub-panels, drawers, message bubbles, and toolbars into reusable components under `src/components/`.
- **Reusable API Client + TanStack Query**: Execute all HTTP calls through a typed API client (`src/lib/apiClient.ts`) consumed via TanStack Query (`useQuery`, `useMutation`) hooks. Avoid raw `fetch()` calls inside React components.
- **Custom Hooks for Side Effects & Streams**: Encapsulate SSE (`EventSource`), timers, and subscriptions inside dedicated hooks under `src/hooks/` rather than inline `useEffect` blocks in page/container components.
- **Environment-Driven Configuration**: Read default customer phone numbers, tenant identifiers, and API endpoints from `src/config/env.ts` (`import.meta.env.VITE_*`) rather than hardcoding literals in components or URLs.
