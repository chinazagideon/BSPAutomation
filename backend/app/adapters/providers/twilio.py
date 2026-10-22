"""Twilio WhatsApp BSP Channel Adapter."""

from typing import Any, Dict, Optional

from app.adapters.base import NormalizedInboundEnvelope
from app.adapters.providers.base_recorder import BaseInMemoryWhatsAppAdapter
from app.adapters.whatsapp_dtos import (
    extract_cloud_api_phone_number_id,
    normalize_cloud_api_webhook_payload,
)


class TwilioWhatsAppAdapter(BaseInMemoryWhatsAppAdapter):
    """Twilio WhatsApp Channel Adapter normalizing Twilio form/JSON webhook payloads."""

    provider_name: str = "TWILIO_AFRICA"

    def extract_phone_number_id(self, payload: Dict[str, Any]) -> Optional[str]:
        to_val = payload.get("To") or payload.get("to")
        if to_val:
            return str(to_val).replace("whatsapp:", "").strip()
        return extract_cloud_api_phone_number_id(payload)

    def normalize_inbound_webhook(self, payload: Dict[str, Any]) -> NormalizedInboundEnvelope:
        if "entry" in payload:
            return normalize_cloud_api_webhook_payload(payload, provider_name=self.provider_name)

        phone_number_id = self.extract_phone_number_id(payload)
        sender = str(payload.get("From") or payload.get("from") or "").replace("whatsapp:", "").strip()
        text = str(payload.get("Body") or payload.get("body") or "").strip()
        msg_id = str(payload.get("MessageSid") or payload.get("SmsSid") or "SM_twilio_1")
        button_payload = payload.get("ButtonPayload") or payload.get("ListId")
        media_url = payload.get("MediaUrl0")
        media_type = str(payload.get("MediaContentType0") or "")

        is_audio = "audio" in media_type
        return NormalizedInboundEnvelope(
            provider=self.provider_name,
            phone_number_id=phone_number_id,
            has_message=bool(sender and (text or button_payload or media_url)),
            sender_phone=sender,
            customer_name=str(payload.get("ProfileName") or "Valued Customer"),
            message_id=msg_id,
            message_type="audio" if is_audio else ("interactive" if button_payload else "text"),
            text=f"[VOICE_NOTE_MEDIA_ID: {msg_id}]" if is_audio else text,
            is_audio=is_audio,
            media_id=msg_id if is_audio else None,
            is_interactive=bool(button_payload),
            interactive_id=button_payload,
        )
