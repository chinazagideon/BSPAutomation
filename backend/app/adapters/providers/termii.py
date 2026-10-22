"""Termii WhatsApp BSP Channel Adapter."""

import hashlib
import hmac
from typing import Any, Dict, Optional

from app.adapters.base import NormalizedInboundEnvelope
from app.adapters.providers.base_recorder import BaseInMemoryWhatsAppAdapter
from app.adapters.whatsapp_dtos import (
    extract_cloud_api_phone_number_id,
    normalize_cloud_api_webhook_payload,
)
from app.core.config import settings


class TermiiWhatsAppAdapter(BaseInMemoryWhatsAppAdapter):
    """Termii WhatsApp BSP Channel Adapter normalizing Termii webhook payloads."""

    provider_name: str = "TERMII"

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        sig = headers.get("X-Termii-Signature") or headers.get("x-termii-signature")
        if sig:
            expected = hmac.new(
                key=(secret or settings.TERMII_API_KEY or settings.META_APP_SECRET).encode("utf-8"),
                msg=raw_body,
                digestmod=hashlib.sha512,
            ).hexdigest()
            return hmac.compare_digest(sig, expected)
        return super().verify_webhook_signature(raw_body, headers, secret)

    def extract_phone_number_id(self, payload: Dict[str, Any]) -> Optional[str]:
        if "device_id" in payload:
            return str(payload["device_id"])
        if "channel_id" in payload:
            return str(payload["channel_id"])
        return extract_cloud_api_phone_number_id(payload)

    def normalize_inbound_webhook(self, payload: Dict[str, Any]) -> NormalizedInboundEnvelope:
        if "entry" in payload:
            return normalize_cloud_api_webhook_payload(payload, provider_name=self.provider_name)

        phone_number_id = self.extract_phone_number_id(payload)
        sender = str(payload.get("sender") or payload.get("from") or "")
        text = str(payload.get("message") or payload.get("text") or "").strip()
        msg_id = str(payload.get("message_id") or payload.get("id") or "termii.msg.1")
        interactive_id = payload.get("interactive_id") or payload.get("button_payload")

        return NormalizedInboundEnvelope(
            provider=self.provider_name,
            phone_number_id=phone_number_id,
            has_message=bool(sender and (text or interactive_id)),
            sender_phone=sender,
            customer_name=str(payload.get("contact_name") or "Valued Customer"),
            message_id=msg_id,
            message_type="interactive" if interactive_id else "text",
            text=text,
            is_interactive=bool(interactive_id),
            interactive_id=interactive_id,
        )
