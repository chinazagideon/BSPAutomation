"""WhatsApp Business Solution Provider Adapters with Audited Egress & Typed ACL DTOs."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.adapters.base import WhatsAppBSPPort, CarouselMessage
from app.core.config import settings
from app.core.egress import AuditedHttpClient


# =============================================================================
# META CLOUD WHATSAPP ANTI-CORRUPTION LAYER (ACL) DTO CONTRACTS
# =============================================================================

class MetaTextMessageDTO(BaseModel):
    preview_url: bool = False
    body: str


class MetaSendTextMessageRequestDTO(BaseModel):
    messaging_product: str = "whatsapp"
    recipient_type: str = "individual"
    to: str
    type: str = "text"
    text: MetaTextMessageDTO


class MetaMessageCreatedDTO(BaseModel):
    id: str


class MetaSendMessageResponseDTO(BaseModel):
    messaging_product: str = "whatsapp"
    contacts: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[MetaMessageCreatedDTO]


# =============================================================================
# ADAPTER IMPLEMENTATION
# =============================================================================

class MetaCloudWhatsAppAdapter(WhatsAppBSPPort):
    """Production Meta Cloud API Adapter using AuditedHttpClient Anti-Corruption Layer."""

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
        return {
            "message_id": msg_id,
            "to": to_phone,
            "status": "SENT",
        }

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
        return {
            "message_id": msg_id,
            "to": to_phone,
            "status": "SENT",
        }

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
            "recipient_type": "individual",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or [],
            },
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {
            "message_id": msg_id,
            "to": to_phone,
            "status": "SENT",
            "template": template_name,
        }

    async def send_media_message(
        self,
        to_phone: str,
        media_type: str,
        media_url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        media_payload: Dict[str, Any] = {"link": media_url}
        if caption:
            media_payload["caption"] = caption
        if filename:
            media_payload["filename"] = filename

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": media_type,
            media_type: media_payload,
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {
            "message_id": msg_id,
            "to": to_phone,
            "status": "SENT",
            "media_type": media_type,
        }

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
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": header_text},
                "body": {"text": body_text},
                "action": {
                    "button": button_title[:20],
                    "sections": sections[:10],
                },
            },
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {
            "message_id": msg_id,
            "to": to_phone,
            "status": "SENT",
        }

    async def send_interactive_carousel(
        self,
        to_phone: str,
        carousel: CarouselMessage,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cards = [
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
                    "parameters": {"display_text": card.cta_text, "url": card.cta_url},
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
                "action": {"cards": cards},
            },
        }
        msg_id = await self._execute_meta_egress(payload, phone_number_id=phone_number_id)
        return {
            "message_id": msg_id,
            "to": to_phone,
            "status": "SENT",
        }


class MockWhatsAppBSPAdapter(WhatsAppBSPPort):
    """Local Dev & CI Mock Simulator for WhatsApp BSP interactions."""

    def __init__(self):
        self.sent_messages: List[Dict[str, Any]] = []

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
            "message_id": f"wamid.mock.{len(self.sent_messages) + 1}",
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
            "message_id": f"wamid.mock.interactive.{len(self.sent_messages) + 1}",
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
            "message_id": f"wamid.mock.template.{len(self.sent_messages) + 1}",
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
            "message_id": f"wamid.mock.media.{len(self.sent_messages) + 1}",
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
            "message_id": f"wamid.mock.list.{len(self.sent_messages) + 1}",
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
            "message_id": f"wamid.mock.carousel.{len(self.sent_messages) + 1}",
            "to": to_phone,
            "body": carousel.body_text,
            "cards": [c.model_dump() for c in carousel.cards],
            "status": "DELIVERED",
            "is_mock": True,
        })


_MOCK_WHATSAPP_INSTANCE: Optional[MockWhatsAppBSPAdapter] = None


def get_whatsapp_bsp_adapter(http_client: Optional[AuditedHttpClient] = None) -> WhatsAppBSPPort:
    """
    Factory creating WhatsApp BSP adapter based on configuration.
    In production, strictly binds to the provided http_client or resolves
    from the active application lifespan registry.
    """
    global _MOCK_WHATSAPP_INSTANCE
    if settings.USE_MOCK_WHATSAPP_BSP or not settings.META_CLOUD_API_TOKEN:
        if _MOCK_WHATSAPP_INSTANCE is None:
            _MOCK_WHATSAPP_INSTANCE = MockWhatsAppBSPAdapter()
        return _MOCK_WHATSAPP_INSTANCE

    from app.core.egress import get_default_audited_client
    try:
        resolved_client = http_client or get_default_audited_client()
    except RuntimeError:
        if _MOCK_WHATSAPP_INSTANCE is None:
            _MOCK_WHATSAPP_INSTANCE = MockWhatsAppBSPAdapter()
        return _MOCK_WHATSAPP_INSTANCE

    return MetaCloudWhatsAppAdapter(
        api_token=settings.META_CLOUD_API_TOKEN,
        phone_number_id=settings.META_PHONE_NUMBER_ID,
        http_client=resolved_client,
    )
