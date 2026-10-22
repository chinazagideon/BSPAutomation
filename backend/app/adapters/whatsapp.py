"""WhatsApp BSP Adapter Facade & Dynamic Provider Resolution Entrypoint (ADR-0047)."""

from typing import Optional

from app.adapters.base import CarouselMessage, NormalizedInboundEnvelope, WhatsAppBSPPort
from app.adapters.providers.dialog360 import Dialog360WhatsAppAdapter
from app.adapters.providers.meta import MetaCloudWhatsAppAdapter
from app.adapters.providers.termii import TermiiWhatsAppAdapter
from app.adapters.providers.twilio import TwilioWhatsAppAdapter
from app.adapters.registry import WhatsAppProviderRegistry
from app.adapters.whatsapp_dtos import (
    MetaMessageCreatedDTO,
    MetaSendMessageResponseDTO,
    MetaSendTextMessageRequestDTO,
    MetaTextMessageDTO,
    extract_cloud_api_phone_number_id,
    normalize_cloud_api_webhook_payload,
)
from app.core.egress import AuditedHttpClient
from app.sandbox.adapter import SandboxWhatsAppBSPAdapter

# Backwards-compatible alias for unit tests importing MockWhatsAppBSPAdapter
MockWhatsAppBSPAdapter = SandboxWhatsAppBSPAdapter


def get_whatsapp_bsp_adapter(
    http_client: Optional[AuditedHttpClient] = None,
    provider_slug: Optional[str] = None,
) -> WhatsAppBSPPort:
    """Resolves a WhatsAppBSPPort adapter dynamically via WhatsAppProviderRegistry."""
    return WhatsAppProviderRegistry.resolve(
        provider_slug=provider_slug,
        http_client=http_client,
    )


__all__ = [
    "CarouselMessage",
    "Dialog360WhatsAppAdapter",
    "MetaCloudWhatsAppAdapter",
    "MetaMessageCreatedDTO",
    "MetaSendMessageResponseDTO",
    "MetaSendTextMessageRequestDTO",
    "MetaTextMessageDTO",
    "MockWhatsAppBSPAdapter",
    "NormalizedInboundEnvelope",
    "SandboxWhatsAppBSPAdapter",
    "TermiiWhatsAppAdapter",
    "TwilioWhatsAppAdapter",
    "WhatsAppBSPPort",
    "WhatsAppProviderRegistry",
    "extract_cloud_api_phone_number_id",
    "get_whatsapp_bsp_adapter",
    "normalize_cloud_api_webhook_payload",
]
