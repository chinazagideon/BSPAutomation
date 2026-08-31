# 9. NEPA Heartbeat Timeout and Transparent Failover

We decided to set the human agent heartbeat timeout threshold at 60 seconds (two consecutive missed 30-second heartbeats), marking the agent `OFFLINE_NEPA`.

Power and ISP outages are frequent in Nigerian urban centers. When a desk drops offline, the system preserves the customer's queue position, transparently sends an informative status message to WhatsApp, and dispatches an emergency SMS alert to a standby manager.
