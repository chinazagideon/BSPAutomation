# Agent Desk Context

Handles human escalation, agent availability monitoring in Nigerian infrastructural environments, and zero-repeat context injection.

## Language

**Heartbeat Monitor**:
A real-time telemetry service that tracks agent connectivity and marks agents as `OFFLINE_NEPA` upon detecting 60 seconds of missed heartbeats.
_Avoid_: Status tracker, ping service

**Standby Escalation Dispatcher**:
A background notification service that alerts managers via SMS/WhatsApp when all desk agents in a regional hub drop offline.
_Avoid_: Emergency pager, failover service

**Context Injector**:
A service that pre-populates a human agent's inbox with synthesized intent, budget, and delivery details when a conversation is escalated.
_Avoid_: Chat summary, handoff note

**Fallback Ticket Queue**:
An asynchronous buffer that safely holds customer inquiries with preserved queue positions when human agents are offline.
_Avoid_: Backlog, pending tickets

**Six-Field Synthesized Context Card**:
A structured JSON payload (`executiveSummary`, `detectedBudgetNaira`, `urgencyTier`, `dialect`, `keyBlockers`, `suggestedFirstResponse`) injected into the live agent interface on every escalation to eliminate repeated questions.
_Avoid_: Chat summary, handoff ticket

**Ticket Claim Model**:
An escalation pattern where unassigned tickets (`assigned_agent_id = NULL`) are broadcast simultaneously to all `ONLINE` agents in a regional hub via Server-Sent Events (SSE), secured by atomic SQL conditional updates on first claim.
_Avoid_: Round-robin assignment, forced dispatch

**Power Outage Failover Loop**:
An automated failover state triggered by the ARQ heartbeat cron when 100% of agents in a regional hub are flagged `OFFLINE_NEPA`, dispatching preserved queue position messages to customers and emergency alerts to merchant management.
_Avoid_: Downtime script, offline mode

