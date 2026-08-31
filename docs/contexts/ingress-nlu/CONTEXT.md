# Ingress & NLU Context

Receives, sanitizes, and classifies incoming WhatsApp conversations in Nigerian Pidgin and Commercial Slang, dynamically scoring customer signals across game-theoretic funnels (Hot Lead, On Budget, Solution Eccentric, Trust-Seeking, Cold Lead) and executing optimal conversion workflows.

## Language

**Lead Qualification Engine**:
The conversational scoring system that evaluates incoming user signals (urgency, budget constraints, technical depth) to compute optimal routing strategies.
_Avoid_: Lead tracker, scoring script

**Hot Lead Workflow**:
A zero-friction, deterministic fast-path execution triggered by high-intent transactional signals that generates an instant checkout link without LLM generation.
_Avoid_: Instant sale, auto-checkout

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

