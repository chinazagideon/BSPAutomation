"""Local BSP Sandbox WhatsApp Adapter (Isolated inside `app/sandbox/` per ADR-0047)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.adapters.base import CarouselMessage
from app.adapters.providers.base_recorder import BaseInMemoryWhatsAppAdapter, generate_mock_wamid
from app.adapters.whatsapp_dtos import MetaSendMessageResponseDTO
from app.contexts.knowledge.seed_data import DEMO_MERCHANTS
from app.core.config import settings
from app.core.egress import AuditedHttpClient
from app.core.exceptions import WhatsAppDeliveryFailedException, WhatsAppRateLimitedException
from app.core.trace import get_context_merchant_id
from app.sandbox.state import SandboxMessageRecord, get_sandbox_store

_SANDBOX_MERCHANT_PHONE_MAP: Dict[str, str] = {
    str(m["id"]): str(m["whatsapp_phone_number_id"])
    for m in DEMO_MERCHANTS
    if "id" in m and "whatsapp_phone_number_id" in m
}


class SandboxWhatsAppBSPAdapter(BaseInMemoryWhatsAppAdapter):
    """Stateful Local BSP Sandbox Adapter.

    Enforces 24h Customer Service Window rules, fault injection flags, and publishes
    outbound envelopes to `SandboxStateStore` (and optional loopback `AuditedHttpClient`).
    """

    provider_name: str = "LOCAL_SANDBOX"

    def __init__(self, http_client: Optional[AuditedHttpClient] = None):
        super().__init__(http_client=http_client)

    async def _publish_to_sandbox(
        self,
        record: Dict[str, Any],
        interactive_type: Optional[str] = None,
        text: str = "",
        header_text: Optional[str] = None,
        button_title: Optional[str] = None,
        buttons: Optional[List[Dict[str, Any]]] = None,
        list_sections: Optional[List[Dict[str, Any]]] = None,
        carousel_cards: Optional[List[Dict[str, Any]]] = None,
        media: Optional[Dict[str, Any]] = None,
        template: Optional[Dict[str, Any]] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        store = get_sandbox_store()
        faults = await store.get_fault_profile()
        context_m_id = str(get_context_merchant_id() or "")
        target_phone_id = (
            phone_number_id
            or _SANDBOX_MERCHANT_PHONE_MAP.get(context_m_id)
            or "meta_phone_alaba_agro"
        )
        to_phone = str(record.get("to", ""))

        if settings.SANDBOX_LOOPBACK_BASE_URL and self.http_client:
            loopback_url = f"{settings.SANDBOX_LOOPBACK_BASE_URL.rstrip('/')}/api/v1/sandbox/waba/{target_phone_id}/messages"
            await self.http_client.request(
                method="POST",
                url=loopback_url,
                json_body={
                    "messaging_product": "whatsapp",
                    "to": to_phone,
                    "type": interactive_type or "text",
                    "record": record,
                    "text": text,
                },
                headers={"Authorization": "Bearer sandbox_loopback_token"},
                response_dto=MetaSendMessageResponseDTO,
                target_service="LOCAL_SANDBOX_WHATSAPP",
            )

        if faults.force_rate_limit_429:
            raise WhatsAppRateLimitedException("Sandbox Fault Injection: HTTP 429 Too Many Requests from BSP")
        if faults.force_upstream_500:
            raise WhatsAppDeliveryFailedException("Sandbox Fault Injection: HTTP 500 Upstream BSP Outage", status_code=500)

        window_state = await store.check_customer_service_window(target_phone_id, to_phone)
        if not window_state["is_open"] and interactive_type != "template":
            blocked_msg = SandboxMessageRecord(
                id=generate_mock_wamid(scope="blocked"),
                sender="system",
                to_phone=to_phone,
                from_phone=target_phone_id,
                phone_number_id=target_phone_id,
                merchant_id=get_context_merchant_id(),
                text=(
                    f"⛔ [24h Customer Service Window Expired ({window_state['elapsed_hours']}h elapsed)]: "
                    f"Free-form/interactive session message rejected by BSP Governor. "
                    f"Dispatch an approved WhatsApp Template Message to re-open the session."
                ),
                timestamp=datetime.now(timezone.utc).strftime("%H:%M"),
                status="failed",
                interactive_type="system_alert",
                metadata={"window_state": window_state, "blocked_payload": record},
            )
            await store.append_message(blocked_msg)
            record["status"] = "FAILED_24H_WINDOW_EXPIRED"
            return self._record(record)

        delivery_status = "failed" if faults.simulate_delivery_failure else "read"
        if faults.simulate_delivery_failure:
            record["status"] = "FAILED"

        detected_itype = interactive_type
        meta_extra: Dict[str, Any] = {"window_state": window_state}
        if "Dedicated Virtual NUBAN" in text or "Moniepoint MFB" in text:
            if not detected_itype:
                detected_itype = "payment_link"
            meta_extra["bankName"] = "Moniepoint MFB"
            meta_extra["accountNumber"] = "9031842901"

        sandbox_msg = SandboxMessageRecord(
            id=record["message_id"],
            sender="bot",
            to_phone=to_phone,
            from_phone=target_phone_id,
            phone_number_id=target_phone_id,
            merchant_id=get_context_merchant_id(),
            text=text,
            timestamp=datetime.now(timezone.utc).strftime("%H:%M"),
            status=delivery_status,
            interactive_type=detected_itype,
            header_text=header_text,
            button_title=button_title,
            buttons=buttons or [],
            list_sections=list_sections or [],
            carousel_cards=carousel_cards or [],
            media=media,
            template=template,
            metadata=meta_extra,
        )
        await store.append_message(sandbox_msg)
        return self._record(record)

    async def send_text_message(
        self,
        to_phone: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = {
            "message_id": generate_mock_wamid(),
            "to": to_phone,
            "message": message,
            "status": "DELIVERED",
            "is_mock": True,
        }
        return await self._publish_to_sandbox(
            record=rec,
            interactive_type=None,
            text=message,
            phone_number_id=phone_number_id,
        )

    async def send_interactive_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = {
            "message_id": generate_mock_wamid("interactive"),
            "to": to_phone,
            "body": body_text,
            "buttons": buttons,
            "status": "DELIVERED",
            "is_mock": True,
        }
        return await self._publish_to_sandbox(
            record=rec,
            interactive_type="buttons",
            text=body_text,
            buttons=buttons,
            phone_number_id=phone_number_id,
        )

    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = {
            "message_id": generate_mock_wamid("template"),
            "to": to_phone,
            "template": template_name,
            "language": language_code,
            "components": components or [],
            "status": "DELIVERED",
            "is_mock": True,
        }
        rendered_text = f"📋 [Template: {template_name} ({language_code})]"
        if components:
            params = [
                str(p["text"])
                for comp in components
                for p in comp.get("parameters", [])
                if "text" in p
            ]
            if params:
                rendered_text += "\nParameters: " + ", ".join(params)
        return await self._publish_to_sandbox(
            record=rec,
            interactive_type="template",
            text=rendered_text,
            template={"name": template_name, "language": language_code, "components": components or []},
            phone_number_id=phone_number_id,
        )

    async def send_media_message(
        self,
        to_phone: str,
        media_type: str,
        media_url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = {
            "message_id": generate_mock_wamid("media"),
            "to": to_phone,
            "media_type": media_type,
            "media_url": media_url,
            "caption": caption,
            "filename": filename,
            "status": "DELIVERED",
            "is_mock": True,
        }
        return await self._publish_to_sandbox(
            record=rec,
            interactive_type="media",
            text=caption or f"[{media_type.upper()}: {filename or media_url}]",
            media={"type": media_type, "url": media_url, "caption": caption, "filename": filename},
            phone_number_id=phone_number_id,
        )

    async def send_interactive_list(
        self,
        to_phone: str,
        header_text: str,
        body_text: str,
        button_title: str,
        sections: List[Dict[str, Any]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = {
            "message_id": generate_mock_wamid("list"),
            "to": to_phone,
            "header": header_text,
            "body": body_text,
            "button_title": button_title,
            "sections": sections,
            "status": "DELIVERED",
            "is_mock": True,
        }
        return await self._publish_to_sandbox(
            record=rec,
            interactive_type="list",
            text=body_text,
            header_text=header_text,
            button_title=button_title,
            list_sections=sections,
            phone_number_id=phone_number_id,
        )

    async def send_interactive_carousel(
        self,
        to_phone: str,
        carousel: CarouselMessage,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cards_dumped = [c.model_dump() for c in carousel.cards]
        rec = {
            "message_id": generate_mock_wamid("carousel"),
            "to": to_phone,
            "body": carousel.body_text,
            "cards": cards_dumped,
            "status": "DELIVERED",
            "is_mock": True,
        }
        return await self._publish_to_sandbox(
            record=rec,
            interactive_type="carousel",
            text=carousel.body_text,
            carousel_cards=cards_dumped,
            phone_number_id=phone_number_id,
        )
