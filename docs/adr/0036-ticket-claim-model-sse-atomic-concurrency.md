# 36. Ticket Claim Model with Server-Sent Events (SSE) and Atomic Lockout

## Context
When customer inquiries escalate from NLU to the human desk, pushing tickets strictly via round-robin risks routing conversations to agents who stepped away from their terminals without logging out. Conversely, bidirectional WebSockets require complex connection state management and fail frequently over degraded mobile networks.

## Decision
We decided to adopt an unassigned Ticket Claim Model combined with unidirectional Server-Sent Events (SSE) backed by Redis Pub/Sub (`desk:hub:<hub_id>`). When an escalation occurs, a ticket is created with `assigned_agent_id = NULL` and broadcast in real time to all `ONLINE` agents in the merchant's regional hub. An agent claims the ticket via `POST /api/v1/desk/tickets/{id}/claim`, which executes an atomic conditional SQL update (`WHERE id = :id AND assigned_agent_id IS NULL AND status = 'OPEN'`). If multiple agents click simultaneously, exactly one succeeds and others receive HTTP 409 Conflict.

## Consequences
- **Pros**: Zero stale tickets stranded with inactive agents; resilient transport over standard HTTP/2 streaming; zero distributed lock overhead; complete decoupling between Ingress and Desk contexts via domain events.
- **Cons**: Requires human agents to proactively monitor their live dashboard stream to claim tickets.
