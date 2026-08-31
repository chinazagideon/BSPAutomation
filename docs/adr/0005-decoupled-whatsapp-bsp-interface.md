# 5. Decoupled WhatsApp Business Solution Provider (BSP) Interface

We decided to build a provider-agnostic WhatsApp integration interface that supports direct Meta Cloud API and local African BSPs (such as Termii).

Direct Meta Cloud API offers minimal latency, while African BSPs provide local Nigerian Naira billing and automated SMS fallback when customers experience mobile data loss. The decoupled interface isolates webhook processing from vendor-specific payload differences.
