# Ingress & NLU Context

Receives, sanitizes, and classifies incoming WhatsApp conversations in Nigerian Pidgin and Commercial Slang, dynamically scoring customer signals across game-theoretic funnels (Hot Lead, On Budget, Solution Eccentric, Trust-Seeking, Cold Lead) and executing optimal conversion workflows.

## Language

**Lead Qualification Engine**:
The conversational scoring system that evaluates incoming user signals (urgency, budget constraints, technical depth) to compute optimal routing strategies.
_Avoid_: Lead tracker, scoring script

**Hot Lead Workflow**:
A zero-friction, deterministic fast-path execution triggered only after Parameter Convergence on high-intent transactional signals, generating an instant checkout hold without LLM generation.
_Avoid_: Instant sale, auto-checkout, premature billing

**Parametric Search**:
An inventory retrieval workflow triggered by budget-constrained signals (`price <= X`) querying PostgreSQL for exact SKU matches without aggressive upselling.
_Avoid_: Catalog search, product query

**Deep RAG Escalation**:
A document retrieval and technical synthesis pipeline invoked for Solution-Eccentric inquiries that automatically fails over to human handoff if AI confidence falls below threshold.
_Avoid_: AI search, doc reader

**Proof Injection**:
The automated delivery of pre-approved social proof (PDF portfolio, verified reviews, case studies) triggered by skeptical, trust-seeking queries.
_Avoid_: Portfolio sender, review link

**Generative Nurturing**:
The dynamic creation of hyper-specific value propositions tailored to a cold lead's extracted industry vertical (e.g. bakeries, logistics, salons).
_Avoid_: Marketing message, auto-nurture

**Funnel Stage State Machine**:
A session state machine tracking the lead's progression across `discovery`, `evaluation`, `negotiation`, and `checkout`, dictating whether LLMs may generate open text or must use deterministic menus.
_Avoid_: Chat state, conversation phase

**Fast-Path Router**:
A deterministic, sub-millisecond intent classification engine that matches high-frequency Nigerian commercial phrases without calling third-party LLMs.
_Avoid_: Keyword matcher, regex filter

**Dialect Classifier**:
The component that detects whether an incoming message is written in Nigerian Pidgin, Commercial Slang, or Standard English to ensure tone-matched responses.
_Avoid_: Language translator, locale switcher

**Prepaid AI Wallet**:
A merchant-managed Naira account drawn down on a per-token basis when conversations escalate to LLMs beyond bundled quotas.
_Avoid_: Credit balance, token account

**Bundled Token Quota**:
A monthly allocation of LLM tokens included directly in Tier 1 (Mid-Market) subscription plans.
_Avoid_: Free tier tokens, trial credits

**Trigram Fast-Path Search**:
A PostgreSQL `pg_trgm` GIN index matching Nigerian Pidgin phrases and commercial catalog items with typo tolerance and sub-millisecond execution.
_Avoid_: Fuzzy search, text query

**Cascading Hybrid NLU Pipeline**:
A 3-stage hierarchical classification architecture that routes inbound messages sequentially through Trigram Fast-Path (Stage 1), Custom Local Classifier (Stage 2), and Gemini LLM Escalation (Stage 3) based on confidence thresholds and stage state controllers.
_Avoid_: Multi-model ensemble, fallback chain

**Custom Local Classifier**:
An in-process machine learning model (e.g. HuggingFace transformer / ONNX Runtime) trained specifically on localized Nigerian commercial dialogues and Pidgin dialect nuances, providing zero-token intent and dialect classification.
_Avoid_: Local LLM, offline model

**Confidence Escalation Gate**:
A configurable threshold-based decision barrier that evaluates whether a stage's classification confidence meets acceptance criteria before either terminating execution or escalating to the next stage.
_Avoid_: Score check, confidence router

**NLU Stage State Controller**:
An environment-driven and tenant-configurable toggle matrix (`USE_FAST_PATH`, `USE_CUSTOM_MODEL`, `USE_LLM_ESCALATION`) that deterministically enables or bypasses specific stages in the cascading pipeline.
_Avoid_: Feature flag, model switch
**Catalog Manifest**:
A structured, Redis-cached JSON dictionary of a merchant's top SKUs, prices, unit packaging, and delivery policies injected directly into Stage 3 LLM prompt context to eliminate external vector database latency and cost.
_Avoid_: Vector database, catalog table, RAG embeddings

**Voice Note Passthrough**:
An ingestion policy that preserves incoming WhatsApp audio attachments by their immutable media_id without external speech-to-text transcription, logging the media reference and routing to human desk review or prompting text elaboration.
_Avoid_: Audio transcriber, Whisper engine, voice bot

**Fast-Path Distributed Dictionary**:
A Redis-cached trigram and regex rule set populated from ingress.fast_path_dictionary with instantaneous pub/sub eviction on merchant configuration changes, sustaining sub-2ms Stage 1 execution.
_Avoid_: Static regex, dynamic SQL search

**Provider Context Manifest**:
An asynchronously synchronized and cached data object holding merchant-specific WhatsApp Business Account (WABA) metadata (verified business name, operating hours, delivery zones, Meta catalog ID, active promotional offerings) injected into Stage 3 LLM prompts to ground conversational reasoning in live provider state without synchronous API calls.
_Avoid_: WABA settings, provider config, API sync

**Parameter Convergence**:
The verification state where all mandatory parameters of a local tool contract are resolved, unambiguous, and validated against in-memory merchant manifests.
_Avoid_: Form completion, slot readiness

**Clarification Slot-Filling**:
A deterministic, zero-token dialogue turn that presents structured options (via WhatsApp buttons or compact menus) to solicit missing parameters from the customer.
_Avoid_: Bot questioning, parameter prompting

**Negotiation Frame**:
An ephemeral, Redis-backed session state machine holding partially bound tool slots and candidate options with a 15-minute sliding TTL during multi-turn negotiation.
_Avoid_: Draft cart, session memory, temporary order

**WhatsApp Message Debounce Buffer**:
A 1.2-second Redis-backed per-phone aggregation window that concatenates rapid-fire message bursts into a single inbound conversational turn before NLU classification.
_Avoid_: Message queue, delay buffer, burst throttler

**Frame Preservation**:
The retention and TTL extension of an active Negotiation Frame during intermediate intent swerves (e.g. FAQ inquiries or agent handoff), allowing seamless resumption of commercial checkout.
_Avoid_: Session pausing, cart freeze, context parking

**Direct Slot Binding**:
The deterministic assignment of typed slot values extracted directly from WhatsApp interactive payload identifiers without NLP entity parsing.
_Avoid_: Button mapping, quick-reply parsing, ID hook

**Deterministic Cancellation Eviction**:
The instantaneous purging of an active Negotiation Frame from Redis triggered by explicit Nigerian Pidgin or English abort keywords.
_Avoid_: Cart cancellation, session reset, abort command

**Lexical Dialect Analyzer**:
A deterministic slang and dialect detector evaluating localized particles and idioms in parallel to neural intent classification.
_Avoid_: Dialect model, language parser

**Structured Schema Decoupling**:
The strict enforcement of typed Pydantic contracts at the LLM provider boundary with graceful fallback to human agent desk handoff on API failure.
_Avoid_: Direct JSON extraction, loose completion

**Response Orchestrator**:
The post-NLU application coordinator executing between intent classification and egress that retrieves catalog context, invokes response classification, and generates audited channel envelopes.
_Avoid_: Message sender, reply handler, dispatch script

**Response Classifier**:
The deterministic mapping engine converting classified intent, extracted commercial entities, and catalog match states into a targeted Response Strategy.
_Avoid_: Intent mapper, response chooser, action selector

**Response Formatter**:
The component that transforms abstract Response Strategies and offering entities into channel-compliant WhatsApp UI structures (Interactive Lists, 3-Button Cards, Text).
_Avoid_: Template engine, string builder, payload maker

**Egress Payload Envelope**:
A typed, side-effect-free data transfer object encapsulating outbound message type, rendered copy, interactive action elements, and recipient coordinates.
_Avoid_: Send payload, wire body, outbound message

**Dual Interactive ID Scheme**:
The protocol distinguishing catalog exploratory actions (`PRODUCT:{sku}`) from transactional slot binding (`SET_SLOT:{param}:{val}`) within WhatsApp interactive component identifiers.
_Avoid_: Button IDs, payload convention, action keys

**Normalized Inbound Message Envelope**:
A provider-agnostic domain representation of an incoming customer turn (sender identity, message type, text body, interactive callback payload, media reference, or delivery status) translated from external provider webhooks before entering the conversational pipeline.
_Avoid_: Meta payload, raw webhook dict, provider event

**BSP Channel Adapter**:
A pluggable anti-corruption boundary encapsulating both inbound webhook verification/normalization and outbound message/account-management dispatch for a specific WhatsApp provider (Meta Cloud API, Termii, Twilio, 360dialog, or Local Sandbox).
_Avoid_: Provider wrapper, API client, webhook handler

**Local BSP Sandbox**:
A stateful local simulation harness that emulates a WhatsApp Business Solution Provider—signing and dispatching real inbound webhooks into the Ingress pipeline, capturing outbound Egress Payload Envelopes in real time for the Web UI Phone Simulator, and enforcing protocol rules and fault injection.
_Avoid_: Mock array, fake server, UI stub

**Customer Service Window Governor**:
The 24-hour sliding session boundary initiated by a customer's last inbound message within which free-form and interactive session messages are permitted, and outside of which only pre-approved WhatsApp Business Templates may be dispatched.
_Avoid_: Session timer, 24h timeout, template lock

**Sandbox Fault Injection Profile**:
A shared runtime configuration matrix controlling simulated transport and protocol anomalies (HTTP 429 rate-limiting, 5xx upstream outages, duplicate webhook replays, invalid HMAC signatures, and clock-shifted 24-hour window expirations).
_Avoid_: Chaos config, mock error flag, test toggle



