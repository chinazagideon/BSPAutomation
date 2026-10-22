"""Dynamic Provider Registry for WhatsApp Business Solution Providers (ADR-0047)."""

from typing import Callable, Dict, Optional

from app.adapters.base import WhatsAppBSPPort
from app.adapters.providers.dialog360 import Dialog360WhatsAppAdapter
from app.adapters.providers.meta import MetaCloudWhatsAppAdapter
from app.adapters.providers.termii import TermiiWhatsAppAdapter
from app.adapters.providers.twilio import TwilioWhatsAppAdapter
from app.core.config import settings
from app.core.egress import AuditedHttpClient, get_default_audited_client

ProviderBuilder = Callable[[Optional[AuditedHttpClient]], WhatsAppBSPPort]


class WhatsAppProviderRegistry:
    """Declarative registry mapping provider slugs and canonical names to adapter builders."""

    _builders: Dict[str, ProviderBuilder] = {}
    _instances: Dict[str, WhatsAppBSPPort] = {}
    _sandbox_instance: Optional[WhatsAppBSPPort] = None

    @classmethod
    def register(cls, slugs: list[str], builder: ProviderBuilder) -> None:
        for slug in slugs:
            cls._builders[slug.strip().lower()] = builder

    @classmethod
    def get_sandbox_adapter(cls, http_client: Optional[AuditedHttpClient] = None) -> WhatsAppBSPPort:
        from app.sandbox.adapter import SandboxWhatsAppBSPAdapter

        if cls._sandbox_instance is None:
            cls._sandbox_instance = SandboxWhatsAppBSPAdapter(http_client=http_client)
        elif http_client is not None:
            cls._sandbox_instance.http_client = http_client  # type: ignore[attr-defined]
        return cls._sandbox_instance

    @classmethod
    def resolve(
        cls,
        provider_slug: Optional[str] = None,
        http_client: Optional[AuditedHttpClient] = None,
    ) -> WhatsAppBSPPort:
        """Resolves a WhatsAppBSPPort dynamically from the provider registry."""
        raw_slug = (provider_slug or "").strip().lower()
        target_key = raw_slug if raw_slug and raw_slug != "whatsapp" else settings.WHATSAPP_BSP_PROVIDER.lower()

        if target_key in ("sandbox", "local_sandbox"):
            return cls.get_sandbox_adapter(http_client=http_client)

        if target_key in ("meta", "meta_cloud"):
            if settings.USE_MOCK_WHATSAPP_BSP or not settings.META_CLOUD_API_TOKEN:
                return cls.get_sandbox_adapter(http_client=http_client)
            try:
                resolved_client = http_client or get_default_audited_client()
            except RuntimeError:
                return cls.get_sandbox_adapter(http_client=http_client)
            return MetaCloudWhatsAppAdapter(
                api_token=settings.META_CLOUD_API_TOKEN,
                phone_number_id=settings.META_PHONE_NUMBER_ID,
                http_client=resolved_client,
            )

        builder = cls._builders.get(target_key)
        if builder is not None:
            cache_key = target_key
            if cache_key not in cls._instances:
                cls._instances[cache_key] = builder(http_client)
            return cls._instances[cache_key]

        return cls.get_sandbox_adapter(http_client=http_client)


# Register third-party BSP adapters in the registry map
WhatsAppProviderRegistry.register(
    ["termii"],
    lambda http_client: TermiiWhatsAppAdapter(http_client=http_client),
)
WhatsAppProviderRegistry.register(
    ["twilio", "twilio_africa"],
    lambda http_client: TwilioWhatsAppAdapter(http_client=http_client),
)
WhatsAppProviderRegistry.register(
    ["360dialog", "dialog360"],
    lambda http_client: Dialog360WhatsAppAdapter(http_client=http_client),
)
