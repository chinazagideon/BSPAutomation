"""Production Meta Cloud API WhatsApp Adapter."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.adapters.base import CarouselMessage, NormalizedInboundEnvelope, WhatsAppBSPPort
from app.adapters.whatsapp_dtos import (
    MetaSendMessageResponseDTO,
    MetaSendTextMessageRequestDTO,
    MetaTextMessageDTO,
    extract_cloud_api_phone_number_id,
    normalize_cloud_api_webhook_payload,
)
from app.core.config import settings
from app.core.egress import AuditedHttpClient
from app.core.security import verify_meta_webhook_signature


class MetaCloudWhatsAppAdapter(WhatsAppBSPPort):
    """Production Meta Cloud API Adapter using AuditedHttpClient Anti-Corruption Layer."""

    provider_name: str = "META_CLOUD"

    def __init__(
        self,
        api_token: str,
        phone_number_id: str,
        http_client: AuditedHttpClient,
        base_url: str = "https://graph.facebook.com/v20.0",
    ):
        if not isinstance(http_client, AuditedHttpClient):
            raise TypeError("MetaCloudWhatsAppAdapter strictly requires an explicit, managed AuditedHttpClient instance")
        self.api_token = api_token
        self.phone_number_id = phone_number_id
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")
        self._auth_headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        sig = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256")
        if sig:
            return verify_meta_webhook_signature(raw_body, sig, secret or settings.META_APP_SECRET)
        if settings.ENVIRONMENT in ["production", "staging"]:
            return False
        return True

    def extract_phone_number_id(self, payload: Dict[str, Any]) -> Optional[str]:
        return extract_cloud_api_phone_number_id(payload)

    def normalize_inbound_webhook(self, payload: Dict[str, Any]) -> NormalizedInboundEnvelope:
        return normalize_cloud_api_webhook_payload(payload, provider_name=self.provider_name)

    def _resolve_messages_endpoint(self, phone_number_id: Optional[str] = None) -> str:
        target_phone_id = phone_number_id or self.phone_number_id
        return f"{self.base_url}/{target_phone_id}/messages"

    async def _execute_meta_egress(
        self,
        payload: Dict[str, Any] | BaseModel,
        phone_number_id: Optional[str] = None,
    ) -> str:
        """Centralized anti-corruption gateway executing audited Meta Graph API egress calls."""
        url = self._resolve_messages_endpoint(phone_number_id)
        response_dto: MetaSendMessageResponseDTO = await self.http_client.request(
            method="POST",
            url=url,
            json_body=payload,
            headers=self._auth_headers,
            response_dto=MetaSendMessageResponseDTO,
            target_service="META_WHATSAPP_CLOUD",
        )
        return response_dto.messages[0].id if response_dto.messages else "wamid.unknown"

    async def send_text_message(
        self,
        to_phone: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        request_dto = MetaSendTextMessageRequestDTO(
            to=to_phone,
            text=MetaTextMessageDTO(body=message),
        )
        msg_id = await self._execute_meta_egress(request_dto, phone_number_id=phone_number_id)
        return {"message_id": msg_id, "to": to_phone, "status": "SENT"}

    async def send_interactive_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        button_elements = [
            {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"][:20]}}
            for btn in buttons[:3]
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": button_elements},
            },
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {"message_id": msg_id, "to": to_phone, "status": "SENT"}

    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or [],
            },
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {"message_id": msg_id, "to": to_phone, "template": template_name, "status": "SENT"}

    async def send_media_message(
        self,
        to_phone: str,
        media_type: str,
        media_url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        media_object: Dict[str, Any] = {"link": media_url}
        if caption and media_type in ["image", "document"]:
            media_object["caption"] = caption
        if filename and media_type == "document":
            media_object["filename"] = filename

        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": media_type,
            media_type: media_object,
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {"message_id": msg_id, "to": to_phone, "media_type": media_type, "status": "SENT"}

    async def send_interactive_list(
        self,
        to_phone: str,
        header_text: str,
        body_text: str,
        button_title: str,
        sections: List[Dict[str, Any]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": header_text[:60]},
                "body": {"text": body_text[:1024]},
                "action": {
                    "button": button_title[:20],
                    "sections": sections[:10],
                },
            },
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {"message_id": msg_id, "to": to_phone, "status": "SENT"}

    async def send_interactive_carousel(
        self,
        to_phone: str,
        carousel: CarouselMessage,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        card_payloads = [
            {
                "card_index": idx,
                "type": "cta_url",
                "header": {
                    "type": card.header_type,
                    card.header_type: {"link": card.media_url},
                },
                "body": {"text": card.body_text},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": card.cta_text,
                        "url": card.cta_url,
                    },
                },
            }
            for idx, card in enumerate(carousel.cards)
        ]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "carousel",
                "body": {"text": carousel.body_text},
                "action": {"cards": card_payloads},
            },
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {"message_id": msg_id, "to": to_phone, "status": "SENT"}
