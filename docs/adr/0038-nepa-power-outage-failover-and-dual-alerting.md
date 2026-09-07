# 38. NEPA Power Outage Failover and Dual Alerting

## Context
Regional power grid collapse (NEPA/PHCN outage) and local broadband backbone disruptions in Nigeria frequently cause entire support teams in an SME hub to go offline simultaneously. Without automated failover monitoring, inbound customer messages remain stranded in queues indefinitely without response, causing customer churn and reputational damage.

## Decision
We decided to operate an ARQ background cron job (`check_agent_heartbeat_timeouts_job`) running every 30 seconds that transitions agents with `last_heartbeat_at < NOW() - INTERVAL '60 seconds'` to `OFFLINE_NEPA`. When all agents in an active hub drop into `OFFLINE_NEPA` while open tickets exist, the system publishes a `HubPowerOutageDetectedEvent`. Desk's `Standby Escalation Dispatcher` alerts the merchant manager via WhatsApp utility template with automatic fallback to cellular SMS (Termii), while Ingress automatically dispatches a polite WhatsApp message to waiting customers informing them of their saved queue position.

## Consequences
- **Pros**: Transparent failover protection; preserves customer goodwill by communicating queue positions; alerts management instantly even when cellular data connectivity drops via SMS fallback.
- **Cons**: 30-second cron interval means agent offline state detection can take up to 60–90 seconds to trigger failover messages.
