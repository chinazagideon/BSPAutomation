"""360dialog WhatsApp BSP Channel Adapter."""

from app.adapters.providers.base_recorder import BaseInMemoryWhatsAppAdapter


class Dialog360WhatsAppAdapter(BaseInMemoryWhatsAppAdapter):
    """360dialog WhatsApp BSP Channel Adapter (Cloud API-compatible schema)."""

    provider_name: str = "DIALOG360"
