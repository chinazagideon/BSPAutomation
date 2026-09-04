# 40. Three-Tier Token Degradation on Soft Limits and Customer-Facing Priority

## Context

In high-volume SME commercial conversational workflows, internal administrative tasks (such as human agent desk 6-field context card synthesis or back-office ticket classification) consume prepaid AI tokens from the same tenant pool as live, revenue-generating customer WhatsApp conversations. Under flat exhaustion thresholds, a burst of internal agent escalations can exhaust a merchant's token balance, causing active customer shopping chats to abruptly fail or drop to static fallback menus midway through negotiations.

## Decision

We decided to implement a **Three-Tier Degradation on Soft Limits** mechanism inside `core.ai_wallets`, inspired by tenant throttling patterns in Cloudflare Workers AI and AWS Bedrock:

1. **Normal Tier (`> 2,000 tokens`)**:
   All caller contexts (`ingress`, `agent-desk`, `reservations`, `checkout-ledger`) may freely invoke external LLM reasoning (Gemini 3.7 Flash) under their requested `ExecutionPolicy`.
2. **Conservation Soft Cap (`1 to 2,000 tokens`)**:
   Non-essential internal and back-office tasks (such as `agent-desk` 6-field context card generation) are throttled and forced into local deterministic mode (`FallbackFactory` regex/templates). The remaining balance is exclusively reserved for direct, customer-facing WhatsApp conversational turns (`TaskPriority.CUSTOMER_FACING`).
3. **Hard Cap (`<= 0 tokens` with ADR-0032 1,000-token leeway consumed)**:
   All contexts immediately degrade to local fast-path trigrams, static button menus, and human desk escalation.

Every generation request must declare a `task_priority: TaskPriority` (`CUSTOMER_FACING` or `INTERNAL_ADMIN`). The generation runtime checks this priority against the merchant's current tier before reserving tokens.

## Consequences

- **Pros**:
  - Protects live customer transactions from interruption caused by background administrative workloads.
  - Transparently extends merchant operating longevity during low-balance periods without requiring emergency manual top-ups.
  - Deterministic internals with configurable interfaces maintain business continuity across all modules.
- **Cons**:
  - Requires callers to specify `task_priority` on generation requests.
  - Desk agents receive deterministic heuristic summary cards rather than deep LLM synthesis when the merchant wallet is in the Conservation Soft Cap tier.
