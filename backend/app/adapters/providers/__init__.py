"""WhatsApp BSP Provider Adapters Package."""

from app.adapters.providers.base_recorder import BaseInMemoryWhatsAppAdapter
from app.adapters.providers.dialog360 import Dialog360WhatsAppAdapter
from app.adapters.providers.meta import MetaCloudWhatsAppAdapter
from app.adapters.providers.termii import TermiiWhatsAppAdapter
from app.adapters.providers.twilio import TwilioWhatsAppAdapter

__all__ = [
    "BaseInMemoryWhatsAppAdapter",
    "Dialog360WhatsAppAdapter",
    "MetaCloudWhatsAppAdapter",
    "TermiiWhatsAppAdapter",
    "TwilioWhatsAppAdapter",
]
