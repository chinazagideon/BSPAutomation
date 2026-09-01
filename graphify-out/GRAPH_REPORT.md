# Graph Report - .  (2026-08-31)

## Corpus Check
- Corpus is ~21,863 words - fits in a single context window. You may not need a graph.

## Summary
- 249 nodes · 309 edges · 28 communities (15 shown, 13 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 17 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- React UI Simulator & Views
- Architecture Decision Records (ADRs)
- PostgreSQL Constraints & Schema
- Runtime Dependencies
- TypeScript Compiler Configuration
- Development Build Tooling
- Agent Desk & Handoff PRD
- Checkout & Ledger Settlement
- Package Scripts & Metadata
- Ingress NLU & Pidgin Search
- NDPA Compliance & PII Vault
- Core Entity Relationship Models
- Backend Express Server & Gemini
- Async Payment & Webhook Architecture
- Consent Audit Ledger
- AI Token Quota
- Lead Generative Nurturing
- Prepaid AI Wallet
- Transaction Proof Injection
- Compliance Domain Schema
- Core Domain Schema
- Desk Domain Schema
- AI Wallet Table
- Ingress Domain Schema
- Ledger Domain Schema
- Reservations Domain Schema
- Consent Event Entity

## God Nodes (most connected - your core abstractions)
1. `Database Schema Design Reference & Specification` - 17 edges
2. `compilerOptions` - 15 edges
3. `Checkout & Ledger Bounded Context` - 12 edges
4. `Ingress & NLU Bounded Context` - 9 edges
5. `scripts` - 7 edges
6. `ADR 0001: Multi-Context Bounded Architecture` - 7 edges
7. `Project Handoff Document: Enterprise Conversational Workflow Platform for Nigerian SMEs` - 7 edges
8. `LeadScore` - 6 edges
9. `MERCHANT Entity Model` - 6 edges
10. `ChatMessage` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Heartbeat Monitor` --semantically_similar_to--> `Resilient No-Repeat Human Handoff Protocol`  [INFERRED] [semantically similar]
  docs/contexts/agent-desk/CONTEXT.md → prd/Project Handoff Document_ Enterprise Conversational Workflow Platform for Nigerian SMEs.pdf
- `Hyper-Localized NLP (Pidgin & Commercial Slang)` --conceptually_related_to--> `Ingress & NLU Bounded Context`  [INFERRED]
  README.md → CONTEXT-MAP.md
- `Infrastructure Resiliency (Anti-Ghosting Queue)` --conceptually_related_to--> `Checkout & Ledger Bounded Context`  [INFERRED]
  README.md → CONTEXT-MAP.md
- `OPEX Protection (Naira Billing & LLM Token Controls)` --conceptually_related_to--> `Checkout & Ledger Bounded Context`  [INFERRED]
  README.md → CONTEXT-MAP.md
- `ADR 0005: Decoupled WhatsApp Business Solution Provider (BSP) Interface` --implements--> `Ingress & NLU Bounded Context`  [EXTRACTED]
  docs/adr/0005-decoupled-whatsapp-bsp-interface.md → CONTEXT-MAP.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Multi-Context Domain Architecture** — context_map_ingress_nlu_context, context_map_checkout_ledger_context, context_map_reservations_context, context_map_agent_desk_context, context_map_compliance_privacy_context [EXTRACTED 1.00]
- **Moniepoint Virtual NUBAN Settlement & 4-Leg Ledger Flow** — docs_adr_0004_swappable_moniepoint_payment_adapter_moniepoint_payment_adapter, docs_adr_0012_four_leg_double_entry_accounting_four_leg_settlement_ledger, docs_adr_0013_dynamic_virtual_nuban_session_matching_dynamic_virtual_nuban_matching, docs_adr_0017_kobo_precision_three_table_ledger_kobo_precision_three_table_ledger [INFERRED 0.95]
- **NDPA 2023 Compliance & Ephemeral Token Vaulting** — docs_adr_0010_ephemeral_encrypted_pii_token_vault_ephemeral_pii_token_vault, docs_adr_0014_deterministic_ndpa_optout_keywords_ndpa_optout_interception, context_map_compliance_privacy_context [INFERRED 0.95]
- **Anti-Ghosting Asynchronous Bank Transfer and Settlement Flow** — docs_contexts_checkout_ledger_context_anti_ghosting_cart, docs_adr_0018_virtual_nuban_pool_quarantine_virtual_nuban_pool_quarantine, marmaid_payment_timeout_flow_2026_08_29_005726_reconciliation_workflow, prd_project_handoff_document_enterprise_conversational_workflow_platform_for_nigerian_smes_anti_ghosting_checkout [INFERRED 0.95]
- **Nigerian Pidgin and Slang Fast-Path NLU Pipeline** — docs_adr_0022_gin_trigram_indexing_nigerian_slang_gin_trigram_indexing, docs_contexts_ingress_nlu_context_fast_path_router, docs_contexts_ingress_nlu_context_trigram_fast_path_search, docs_schema_schema_design_ingress_slang_dictionary, prd_project_handoff_document_enterprise_conversational_workflow_platform_for_nigerian_smes_pidgin_slang_nlu [INFERRED 0.95]
- **NDPA 2023 Cryptographic Consent and Privacy Assurance System** — docs_adr_0020_sha256_chained_consent_ledger_sha256_chained_consent_ledger, docs_contexts_compliance_context_chained_consent_ledger, docs_contexts_compliance_context_pii_sanitizer, docs_schema_schema_design_compliance_consent_events, prd_project_handoff_document_enterprise_conversational_workflow_platform_for_nigerian_smes_ndpa_pii_security [INFERRED 0.95]

## Communities (28 total, 13 thin omitted)

### Community 0 - "React UI Simulator & Views"
Cohesion: 0.09
Nodes (38): AntiGhostingLedger(), AntiGhostingLedgerProps, AtomicReservationGrid(), AtomicReservationGridProps, Header(), HeaderProps, NluIntentMatrix(), NluIntentMatrixProps (+30 more)

### Community 1 - "Architecture Decision Records (ADRs)"
Cohesion: 0.14
Nodes (26): Agent Desk Bounded Context, Checkout & Ledger Bounded Context, Compliance & Privacy Bounded Context, Ingress & NLU Bounded Context, Reservations Bounded Context, ADR 0001: Multi-Context Bounded Architecture, ADR 0002: Python FastAPI & AsyncIO Core Backend, ADR 0003: Dual-Layer PostgreSQL GiST and Redis Reservation Holds (+18 more)

### Community 2 - "PostgreSQL Constraints & Schema"
Cohesion: 0.10
Nodes (22): Partial GiST Temporal Exclusion Constraint on Active Reservation Slots, PostgreSQL TSTZRANGE GiST Exclusion Constraint, Check Constraints over Native PostgreSQL Enums for Zero-Downtime Migrations, Zero-Downtime Schema Alterations, Anti-No-Show Hold, Atomic Slot, Partial GiST Temporal Lock, Reservations Bounded Context (+14 more)

### Community 3 - "Runtime Dependencies"
Cohesion: 0.10
Nodes (21): dotenv, express, @google/genai, lucide-react, motion, dependencies, dotenv, express (+13 more)

### Community 4 - "TypeScript Compiler Configuration"
Cohesion: 0.11
Nodes (18): DOM, DOM.Iterable, ES2022, compilerOptions, allowImportingTsExtensions, allowJs, experimentalDecorators, isolatedModules (+10 more)

### Community 5 - "Development Build Tooling"
Cohesion: 0.13
Nodes (15): autoprefixer, esbuild, devDependencies, autoprefixer, esbuild, tailwindcss, tsx, @types/express (+7 more)

### Community 6 - "Agent Desk & Handoff PRD"
Cohesion: 0.14
Nodes (14): Agent Desk Bounded Context, Context Injector, Fallback Ticket Queue, Heartbeat Monitor, Six-Field Synthesized Context Card, Standby Escalation Dispatcher, Anti-Ghosting Asynchronous Checkout Infrastructure, Tier 1 Mid-Market Enterprise Profile (+6 more)

### Community 7 - "Checkout & Ledger Settlement"
Cohesion: 0.15
Nodes (13): 30-Minute Cooldown Quarantine, NIBSS Instant Payment Settlement Collision Prevention, Pre-Provisioned Virtual NUBAN Pool with Cooldown Quarantine, Anti-Ghosting Cart, Checkout & Ledger Bounded Context, Double-Entry Reconciler, Dynamic Virtual NUBAN, 4-Leg Double-Entry Settlement (+5 more)

### Community 8 - "Package Scripts & Metadata"
Cohesion: 0.17
Nodes (11): name, private, scripts, build, clean, dev, lint, preview (+3 more)

### Community 9 - "Ingress NLU & Pidgin Search"
Cohesion: 0.18
Nodes (11): PostgreSQL GIN Trigram Indexing for Nigerian Slang and Catalog Matching, PostgreSQL pg_trgm Extension, Deep RAG Escalation, Dialect Classifier, Fast-Path Router, Funnel Stage State Machine, Hot Lead Workflow, Ingress & NLU Bounded Context (+3 more)

### Community 10 - "NDPA Compliance & PII Vault"
Cohesion: 0.25
Nodes (8): Nigeria Data Protection Commission (NDPC) Verification, SHA-256 Chained Event-Sourced NDPA Consent Audit Ledger, Chained Consent Ledger, Compliance & Privacy Bounded Context, Ephemeral Token Vault, Opt-Out Interceptor, PII Sanitizer, Redaction Token

### Community 11 - "Core Entity Relationship Models"
Cohesion: 0.36
Nodes (8): ATOMIC_SLOT Entity Model, CHECKOUT_CART Entity Model, CONVERSATION Entity Model, BAS for Nigeria SMEs Entity-Relationship Diagram, ESCALATION_TICKET Entity Model, JOURNAL_ENTRY Entity Model, MERCHANT Entity Model, VIRTUAL_NUBAN Entity Model

### Community 12 - "Backend Express Server & Gemini"
Cohesion: 0.25
Nodes (3): app, stats, SystemStats

### Community 13 - "Async Payment & Webhook Architecture"
Cohesion: 0.29
Nodes (7): Celery Asynchronous Worker, FastAPI Webhook Gateway, Moniepoint MFB Integration Rail, Asynchronous Deterministic Settlement Flow, Redis Inbound Event Queue, Payment Timeout and Asynchronous Settlement Sequence Diagram, spaCy NLU Intent Parser

## Knowledge Gaps
- **110 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+105 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database Schema Design Reference & Specification` connect `PostgreSQL Constraints & Schema` to `Ingress NLU & Pidgin Search`, `NDPA Compliance & PII Vault`, `Checkout & Ledger Settlement`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `dependencies` connect `Runtime Dependencies` to `Package Scripts & Metadata`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Why does `devDependencies` connect `Development Build Tooling` to `Package Scripts & Metadata`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Checkout & Ledger Bounded Context` (e.g. with `Infrastructure Resiliency (Anti-Ghosting Queue)` and `OPEX Protection (Naira Billing & LLM Token Controls)`) actually correct?**
  _`Checkout & Ledger Bounded Context` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _110 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `React UI Simulator & Views` be split into smaller, more focused modules?**
  _Cohesion score 0.08549019607843138 - nodes in this community are weakly interconnected._
- **Should `Architecture Decision Records (ADRs)` be split into smaller, more focused modules?**
  _Cohesion score 0.13538461538461538 - nodes in this community are weakly interconnected._