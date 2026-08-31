"""WhatsApp Business Solution Provider Adapters with Audited Egress & Typed ACL DTOs."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.adapters.base import WhatsAppBSPPort
from app.core.config import settings
from app.core.egress import AuditedHttpClient, audited_http_client


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
        http_client: Optional[AuditedHttpClient] = None,
    ):
        self.api_token = api_token
        self.phone_number_id = phone_number_id
        self.http_client = http_client or audited_http_client

    async def send_text_message(
        self,
        to_phone: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_phone_id = phone_number_id or self.phone_number_id
        url = f"https://graph.facebook.com/v20.0/{target_phone_id}/messages"
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

        request_dto = MetaSendTextMessageRequestDTO(
            to=to_phone,
            text=MetaTextMessageDTO(body=message),
        )

        response_dto: MetaSendMessageResponseDTO = await self.http_client.request(
            method="POST",
            url=url,
            json_body=request_dto,
            headers=headers,
            response_dto=MetaSendMessageResponseDTO,
            target_service="META_WHATSAPP_CLOUD",
        )

        msg_id = response_dto.messages[0].id if response_dto.messages else "wamid.unknown"
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
        target_phone_id = phone_number_id or self.phone_number_id
        url = f"https://graph.facebook.com/v20.0/{target_phone_id}/messages"
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

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

        response_dto: MetaSendMessageResponseDTO = await self.http_client.request(
            method="POST",
            url=url,
            json_body=payload,
            headers=headers,
            response_dto=MetaSendMessageResponseDTO,
            target_service="META_WHATSAPP_CLOUD",
        )

        msg_id = response_dto.messages[0].id if response_dto.messages else "wamid.unknown"
        return {
            "message_id": msg_id,
            "to": to_phone,
            "status": "SENT",
        }


class MockWhatsAppBSPAdapter(WhatsAppBSPPort):
    """Local Dev & CI Mock Simulator for WhatsApp BSP interactions."""

    def __init__(self):
        self.sent_messages: List[Dict[str, Any]] = []

    async def send_text_message(
        self,
        to_phone: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = {
            "message_id": f"wamid.mock.{len(self.sent_messages) + 1}",
            "to": to_phone,
            "message": message,
            "status": "DELIVERED",
            "is_mock": True,
        }
        self.sent_messages.append(record)
        return record

    async def send_interactive_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = {
            "message_id": f"wamid.mock.interactive.{len(self.sent_messages) + 1}",
            "to": to_phone,
            "body": body_text,
            "buttons": buttons,
            "status": "DELIVERED",
            "is_mock": True,
        }
        self.sent_messages.append(record)
        return record


def get_whatsapp_bsp_adapter(http_client: Optional[AuditedHttpClient] = None) -> WhatsAppBSPPort:
    """Factory creating WhatsApp BSP adapter based on configuration."""
    if settings.USE_MOCK_WHATSAPP_BSP or not settings.META_CLOUD_API_TOKEN:
        return MockWhatsAppBSPAdapter()
    return MetaCloudWhatsAppAdapter(
        settings.META_CLOUD_API_TOKEN,
        settings.META_PHONE_NUMBER_ID,
        http_client=http_client,
    )
