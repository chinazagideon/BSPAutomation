"""Local In-Memory Recorder Adapter Base for Non-Meta / Test BSP Implementations."""

import uuid
from typing import Any, Dict, List, Optional

from app.adapters.base import CarouselMessage, NormalizedInboundEnvelope, WhatsAppBSPPort
from app.adapters.whatsapp_dtos import (
    extract_cloud_api_phone_number_id,
    normalize_cloud_api_webhook_payload,
)
from app.core.config import settings
from app.core.egress import AuditedHttpClient
from app.core.security import verify_meta_webhook_signature


class BaseInMemoryWhatsAppAdapter(WhatsAppBSPPort):
    """Lightweight in-memory recorder base class with zero sandbox coupling."""

    provider_name: str = "MOCK_BSP"

    def __init__(self, http_client: Optional[AuditedHttpClient] = None):
        self.sent_messages: List[Dict[str, Any]] = []
        self.http_client = http_client

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        sig = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256")
        if sig:
            return verify_meta_webhook_signature(raw_body, sig, secret or settings.META_APP_SECRET)
        return True

    def extract_phone_number_id(self, payload: Dict[str, Any]) -> Optional[str]:
        return extract_cloud_api_phone_number_id(payload)

    def normalize_inbound_webhook(self, payload: Dict[str, Any]) -> NormalizedInboundEnvelope:
        return normalize_cloud_api_webhook_payload(payload, provider_name=self.provider_name)

    def clear(self) -> None:
        """Purges recorded messages in memory."""
        self.sent_messages.clear()

    def _record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self.sent_messages.append(record)
        return record

    async def send_text_message(
        self,
        to_phone: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record({
            "message_id": f"wamid.mock.{uuid.uuid4().hex[:8]}",
            "to": to_phone,
            "message": message,
            "status": "DELIVERED",
            "is_mock": True,
        })

    async def send_interactive_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record({
            "message_id": f"wamid.mock.interactive.{uuid.uuid4().hex[:8]}",
            "to": to_phone,
            "body": body_text,
            "buttons": buttons,
            "status": "DELIVERED",
            "is_mock": True,
        })

    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record({
            "message_id": f"wamid.mock.template.{uuid.uuid4().hex[:8]}",
            "to": to_phone,
            "template": template_name,
            "language": language_code,
            "components": components or [],
            "status": "DELIVERED",
            "is_mock": True,
        })

    async def send_media_message(
        self,
        to_phone: str,
        media_type: str,
        media_url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record({
            "message_id": f"wamid.mock.media.{uuid.uuid4().hex[:8]}",
            "to": to_phone,
            "media_type": media_type,
            "media_url": media_url,
            "caption": caption,
            "filename": filename,
            "status": "DELIVERED",
            "is_mock": True,
        })

    async def send_interactive_list(
        self,
        to_phone: str,
        header_text: str,
        body_text: str,
        button_title: str,
        sections: List[Dict[str, Any]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record({
            "message_id": f"wamid.mock.list.{uuid.uuid4().hex[:8]}",
            "to": to_phone,
            "header": header_text,
            "body": body_text,
            "button_title": button_title,
            "sections": sections,
            "status": "DELIVERED",
            "is_mock": True,
        })

    async def send_interactive_carousel(
        self,
        to_phone: str,
        carousel: CarouselMessage,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record({
            "message_id": f"wamid.mock.carousel.{uuid.uuid4().hex[:8]}",
            "to": to_phone,
            "body": carousel.body_text,
            "cards": [c.model_dump() for c in carousel.cards],
            "status": "DELIVERED",
            "is_mock": True,
        })
