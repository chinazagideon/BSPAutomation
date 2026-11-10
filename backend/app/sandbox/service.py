"""Sandbox Orchestration Service encapsulating webhook synthesis, HMAC signing, and simulation workflows (ADR-0047)."""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status

from app.adapters.whatsapp import get_whatsapp_bsp_adapter
from app.contexts.knowledge.seed_data import ALABA_AGRO_MERCHANT_ID, DEMO_MERCHANTS
from app.core.config import settings
from app.sandbox.schemas import (
    SandboxBurstRequest,
    SandboxInboundRequest,
    SandboxTemplateSendRequest,
)
from app.sandbox.state import SandboxMessageRecord, get_sandbox_store


class SandboxPayloadFactory:
    """Builds provider-specific webhook payloads and HMAC signatures for sandbox simulation."""

    @staticmethod
    def build_webhook_payload(req: SandboxInboundRequest, msg_id: str) -> Dict[str, Any]:
        prov = req.provider.lower()
        if prov == "termii":
            return {
                "device_id": req.phone_number_id,
                "sender": req.customer_phone,
                "contact_name": req.customer_name,
                "message_id": msg_id,
                "message": req.text,
                "interactive_id": req.interactive_id,
            }
        if prov in ("twilio", "twilio_africa"):
            payload: Dict[str, Any] = {
                "To": f"whatsapp:{req.phone_number_id}",
                "From": f"whatsapp:{req.customer_phone}",
                "ProfileName": req.customer_name,
                "MessageSid": msg_id,
                "Body": req.text,
            }
            if req.interactive_id:
                payload["ButtonPayload"] = req.interactive_id
            if req.message_type == "audio":
                payload["MediaUrl0"] = f"https://sandbox.local/audio/{req.media_id or msg_id}.ogg"
                payload["MediaContentType0"] = "audio/ogg"
            return payload

        value_obj: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "2348011223301",
                "phone_number_id": req.phone_number_id,
            },
            "contacts": [
                {
                    "profile": {"name": req.customer_name},
                    "wa_id": req.customer_phone.lstrip("+"),
                }
            ],
        }

        if req.message_type == "status":
            value_obj["statuses"] = [
                {
                    "id": req.status_message_id or f"wamid.status.{uuid.uuid4().hex[:8]}",
                    "status": req.status_value or "read",
                    "timestamp": str(int(time.time())),
                    "recipient_id": req.customer_phone.lstrip("+"),
                }
            ]
        else:
            msg_obj: Dict[str, Any] = {
                "from": req.customer_phone.lstrip("+"),
                "id": msg_id,
                "timestamp": str(int(time.time())),
            }
            if req.message_type == "button_reply":
                msg_obj["type"] = "interactive"
                msg_obj["interactive"] = {
                    "type": "button_reply",
                    "button_reply": {
                        "id": req.interactive_id or "BTN_1",
                        "title": req.text or req.interactive_id or "Button",
                    },
                }
            elif req.message_type == "list_reply":
                msg_obj["type"] = "interactive"
                msg_obj["interactive"] = {
                    "type": "list_reply",
                    "list_reply": {
                        "id": req.interactive_id or "LIST_1",
                        "title": req.text or req.interactive_id or "List Item",
                    },
                }
            elif req.message_type in ("audio", "voice"):
                media_id = req.media_id or f"media.vn.{uuid.uuid4().hex[:8]}"
                msg_obj["type"] = "audio"
                msg_obj["audio"] = {
                    "id": media_id,
                    "mime_type": "audio/ogg; codecs=opus",
                    "voice": True,
                }
            elif req.message_type == "reaction":
                msg_obj["type"] = "reaction"
                msg_obj["reaction"] = {
                    "message_id": req.status_message_id or "wamid.prev",
                    "emoji": req.reaction_emoji or "👍",
                }
            elif req.message_type == "location":
                msg_obj["type"] = "location"
                msg_obj["location"] = req.location or {
                    "latitude": 6.6018,
                    "longitude": 3.3515,
                    "name": "Allen Avenue, Ikeja",
                    "address": "Ikeja, Lagos",
                }
            elif req.message_type == "unsupported":
                msg_obj["type"] = "contacts"
            else:
                msg_obj["type"] = "text"
                msg_obj["text"] = {"body": req.text}

            value_obj["messages"] = [msg_obj]

        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_SANDBOX_NG_01",
                    "changes": [
                        {
                            "value": value_obj,
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

    @staticmethod
    def compute_hmac_signature(raw_body: bytes, corrupt: bool = False) -> str:
        if corrupt:
            return "sha256=00000000000000000000000000000000000000000000000000000000deadbeef"
        digest = hmac.new(
            key=settings.META_APP_SECRET.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"


class SandboxOrchestrationService:
    """Application service coordinating Local BSP Sandbox simulation, state snapshots, and fault injection."""

    @staticmethod
    async def ensure_sandbox_tenant(phone_number_id: str) -> str:
        from app.contexts.core.services import MerchantIdentificationService
        from app.contexts.knowledge.seeder import CatalogSeeder
        from app.core.database import async_session_factory

        channel_ctx = await MerchantIdentificationService.resolve_inbound(phone_number_id)
        merchant_id = channel_ctx.merchant_id if channel_ctx else None
        if not merchant_id:
            try:
                async with async_session_factory() as seed_session:
                    await CatalogSeeder.seed_all(session=seed_session, reset=False)
                channel_ctx = await MerchantIdentificationService.resolve_inbound(phone_number_id)
                merchant_id = channel_ctx.merchant_id if channel_ctx else None
            except Exception:
                merchant_id = str(ALABA_AGRO_MERCHANT_ID)
        return merchant_id or str(ALABA_AGRO_MERCHANT_ID)

    @classmethod
    async def get_state_snapshot(cls, phone_number_id: str, customer_phone: str) -> Dict[str, Any]:
        from app.contexts.core.services import MerchantIdentificationService
        from app.core.generation.negotiation import NegotiationFrameManager

        store = get_sandbox_store()
        faults = await store.get_fault_profile()
        nlu_ctrl = await store.get_nlu_controller()
        window = await store.check_customer_service_window(phone_number_id, customer_phone)
        messages = await store.get_messages(phone_number_id=phone_number_id)
        webhook_logs = await store.get_webhook_logs()
        nlu_traces = await store.get_nlu_traces()
        telemetry_events = await store.get_telemetry_events(limit=100)

        channel_ctx = await MerchantIdentificationService.resolve_inbound(phone_number_id)
        merchant_id = channel_ctx.merchant_id if channel_ctx else str(ALABA_AGRO_MERCHANT_ID)
        stack = await NegotiationFrameManager.load_stack(merchant_id, customer_phone.lstrip("+"))
        active_frame = stack.active_frame

        return {
            "merchants": [
                {
                    "id": str(m["id"]),
                    "business_name": m["business_name"],
                    "slug": m["slug"],
                    "whatsapp_business_phone": m["whatsapp_business_phone"],
                    "whatsapp_phone_number_id": m["whatsapp_phone_number_id"],
                    "channels": m.get("channels", []),
                }
                for m in DEMO_MERCHANTS
            ],
            "active_merchant_id": merchant_id,
            "active_channel": channel_ctx.model_dump() if channel_ctx else None,
            "phone_number_id": phone_number_id,
            "customer_phone": customer_phone,
            "fault_profile": faults.model_dump(),
            "nlu_controller": nlu_ctrl.model_dump(),
            "window_state": window,
            "active_frame": active_frame.model_dump(mode="json") if active_frame else None,
            "context_stack": [f.model_dump(mode="json") for f in stack.frames],
            "messages": messages,
            "webhook_logs": webhook_logs,
            "nlu_traces": nlu_traces,
            "telemetry_events": telemetry_events,
            "templates": store.get_templates(),
            "jaeger_ui_url": settings.JAEGER_UI_URL,
        }

    @classmethod
    async def handle_loopback_graph_egress(cls, phone_number_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        store = get_sandbox_store()
        faults = await store.get_fault_profile()

        if faults.network_latency_ms > 0:
            await asyncio.sleep(faults.network_latency_ms / 1000.0)

        if faults.force_rate_limit_429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Sandbox Fault Injection: (#130429) Rate limit hit for WABA phone_number_id",
            )

        if faults.force_upstream_500:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Sandbox Fault Injection: Upstream Meta Graph API 500 Internal Error",
            )

        to_phone = str(body.get("to", "2348031234567"))
        msg_id = f"wamid.sandbox.{uuid.uuid4().hex[:12]}"
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": to_phone, "wa_id": to_phone.lstrip("+")}],
            "messages": [{"id": msg_id}],
        }

    @classmethod
    async def dispatch_inbound_turn(cls, req: SandboxInboundRequest, app_state: Any = None) -> Dict[str, Any]:
        from app.contexts.ingress.router import receive_whatsapp_webhook
        from app.core.generation.negotiation import NegotiationFrameManager
        from app.core.worker import _execute_webhook_processing

        store = get_sandbox_store()
        faults = await store.get_fault_profile()
        merchant_id = await cls.ensure_sandbox_tenant(req.phone_number_id)

        msg_id = req.custom_message_id or f"wamid.inbound.{uuid.uuid4().hex[:10]}"
        payload = SandboxPayloadFactory.build_webhook_payload(req, msg_id)
        raw_bytes = json.dumps(payload).encode("utf-8")
        sig_header = SandboxPayloadFactory.compute_hmac_signature(raw_bytes, corrupt=faults.corrupt_hmac_signature)

        if req.message_type != "status":
            display_text = req.text
            if req.message_type == "audio":
                display_text = f"🎤 Voice Note ({req.media_id or 'audio.ogg'})"
            elif req.message_type == "reaction":
                display_text = f"Reacted {req.reaction_emoji or '👍'}"
            elif req.message_type == "location":
                loc_name = (req.location or {}).get("name", "Allen Avenue, Ikeja")
                display_text = f"📍 Shared Location: {loc_name}"

            user_bubble = SandboxMessageRecord(
                id=msg_id,
                sender="user",
                to_phone=req.phone_number_id,
                from_phone=req.customer_phone,
                phone_number_id=req.phone_number_id,
                merchant_id=merchant_id,
                text=display_text,
                timestamp=datetime.now(timezone.utc).strftime("%H:%M"),
                status="read",
                interactive_type="voice_note" if req.message_type == "audio" else None,
                metadata={
                    "message_type": req.message_type,
                    "interactive_id": req.interactive_id,
                    "provider": req.provider,
                },
            )
            await store.append_message(user_bubble)

        scope = {
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/ingress/webhooks/{req.provider}",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-hub-signature-256", sig_header.encode("utf-8")),
            ],
            "query_string": b"",
            "client": ("127.0.0.1", 50000),
        }

        async def receive():
            return {"type": "http.request", "body": raw_bytes, "more_body": False}

        synthetic_request = Request(scope, receive)
        start_ack = time.perf_counter()

        try:
            ack_result = await receive_whatsapp_webhook(provider=req.provider, request=synthetic_request)
            ack_latency_ms = max(1, int((time.perf_counter() - start_ack) * 1000))
        except HTTPException as exc:
            ack_latency_ms = max(1, int((time.perf_counter() - start_ack) * 1000))
            wh_log = {
                "id": f"wh-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "event": f"webhook.rejected ({req.provider})",
                "phone": req.customer_phone,
                "rawPayload": payload,
                "signatureVerified": False,
                "httpStatus": exc.status_code,
                "ackLatencyMs": ack_latency_ms,
                "workerStatus": "rejected",
                "workerLatencyMs": 0,
                "detail": exc.detail,
            }
            await store.append_webhook_log(wh_log)
            err_bubble = SandboxMessageRecord(
                id=f"wamid.err.{uuid.uuid4().hex[:8]}",
                sender="system",
                to_phone=req.customer_phone,
                from_phone=req.phone_number_id,
                phone_number_id=req.phone_number_id,
                merchant_id=merchant_id,
                text=f"🛡️ [Ingress Security Gate HTTP {exc.status_code}]: {exc.detail}",
                timestamp=datetime.now(timezone.utc).strftime("%H:%M"),
                status="failed",
                interactive_type="system_alert",
            )
            await store.append_message(err_bubble)
            return {
                "status": "REJECTED",
                "http_status": exc.status_code,
                "detail": exc.detail,
                "webhook_log": wh_log,
            }

        event_id = ack_result.get("event_id")
        job_id = str(ack_result.get("job_id", ""))
        worker_result = None
        worker_start = time.perf_counter()

        if req.execute_worker_inline or job_id.startswith("mock-job-"):
            try:
                http_client = getattr(app_state, "audited_http_client", None) if app_state else None
                worker_result = await _execute_webhook_processing(
                    ctx={
                        "audited_http_client": http_client,
                        "provider_slug": req.provider,
                    },
                    merchant_id=merchant_id,
                    event_id=event_id,
                    raw_payload=payload,
                    provider_slug=req.provider,
                )
            except Exception as worker_exc:
                worker_result = {"status": "WORKER_ERROR", "error": str(worker_exc)}
                err_bubble = SandboxMessageRecord(
                    id=f"wamid.worker_err.{uuid.uuid4().hex[:8]}",
                    sender="system",
                    to_phone=req.customer_phone,
                    from_phone=req.phone_number_id,
                    phone_number_id=req.phone_number_id,
                    merchant_id=merchant_id,
                    text=f"⚠️ [Egress / Worker Exception]: {worker_exc}",
                    timestamp=datetime.now(timezone.utc).strftime("%H:%M"),
                    status="failed",
                    interactive_type="system_alert",
                )
                await store.append_message(err_bubble)

        if faults.duplicate_webhook_replay and event_id:
            await store.append_webhook_log({
                "id": f"wh-dup-{uuid.uuid4().hex[:6]}",
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "event": f"messages.duplicate_replay ({req.provider})",
                "phone": req.customer_phone,
                "rawPayload": payload,
                "signatureVerified": True,
                "httpStatus": 200,
                "ackLatencyMs": ack_latency_ms,
                "workerStatus": "completed",
                "workerLatencyMs": 2,
            })

        worker_latency_ms = max(1, int((time.perf_counter() - worker_start) * 1000))
        wh_log = {
            "id": event_id or f"wh-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "event": f"messages.{req.message_type} ({req.provider})",
            "phone": req.customer_phone,
            "rawPayload": payload,
            "signatureVerified": ack_result.get("signature_verified", True),
            "httpStatus": 200,
            "ackLatencyMs": ack_result.get("ack_latency_ms", ack_latency_ms),
            "workerStatus": "completed" if (not worker_result or worker_result.get("status") != "WORKER_ERROR") else "retrying",
            "workerLatencyMs": worker_latency_ms,
            "workerResult": worker_result,
        }
        await store.append_webhook_log(wh_log)

        active_frame = await NegotiationFrameManager.get_frame(merchant_id, req.customer_phone.lstrip("+"))
        messages = await store.get_messages(phone_number_id=req.phone_number_id)
        window = await store.check_customer_service_window(req.phone_number_id, req.customer_phone)
        nlu_traces = await store.get_nlu_traces()
        telemetry_events = await store.get_telemetry_events(limit=50)

        return {
            "status": "OK",
            "ack": ack_result,
            "worker_result": worker_result,
            "webhook_log": wh_log,
            "active_frame": active_frame.model_dump(mode="json") if active_frame else None,
            "window_state": window,
            "messages": messages[-10:],
            "latest_nlu_trace": nlu_traces[0] if nlu_traces else None,
            "telemetry_events": telemetry_events,
        }

    @classmethod
    async def dispatch_burst(cls, req: SandboxBurstRequest, app_state: Any = None) -> Dict[str, Any]:
        async def _send_one(idx: int, text_piece: str):
            if idx > 0 and req.inter_message_delay_ms > 0:
                await asyncio.sleep((idx * req.inter_message_delay_ms) / 1000.0)
            sub_req = SandboxInboundRequest(
                provider=req.provider,
                phone_number_id=req.phone_number_id,
                customer_phone=req.customer_phone,
                customer_name=req.customer_name,
                message_type="text",
                text=text_piece,
                execute_worker_inline=True,
            )
            return await cls.dispatch_inbound_turn(sub_req, app_state=app_state)

        results = await asyncio.gather(*[_send_one(i, m) for i, m in enumerate(req.messages)])
        store = get_sandbox_store()
        return {
            "status": "BURST_COMPLETED",
            "burst_count": len(req.messages),
            "results": results,
            "messages": await store.get_messages(phone_number_id=req.phone_number_id),
        }

    @classmethod
    async def send_template(cls, req: SandboxTemplateSendRequest, app_state: Any = None) -> Dict[str, Any]:
        store = get_sandbox_store()
        http_client = getattr(app_state, "audited_http_client", None) if app_state else None
        whatsapp = get_whatsapp_bsp_adapter(http_client=http_client, provider_slug="sandbox")

        components = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in req.parameters],
            }
        ]
        res = await whatsapp.send_template_message(
            to_phone=req.to_phone,
            template_name=req.template_name,
            language_code=req.language_code,
            components=components,
            phone_number_id=req.phone_number_id,
        )
        return {
            "status": "TEMPLATE_SENT",
            "result": res,
            "messages": await store.get_messages(phone_number_id=req.phone_number_id),
        }

    @classmethod
    async def reset_session(cls, phone_number_id: str, customer_phone: str) -> Dict[str, Any]:
        from app.contexts.core.services import MerchantIdentificationService

        store = get_sandbox_store()
        channel_ctx = await MerchantIdentificationService.resolve_inbound(phone_number_id)
        merchant_id = channel_ctx.merchant_id if channel_ctx else str(ALABA_AGRO_MERCHANT_ID)
        await store.clear_conversation(merchant_id=merchant_id, customer_phone=customer_phone.lstrip("+"))
        await store.update_fault_profile({
            "force_rate_limit_429": False,
            "force_upstream_500": False,
            "simulate_delivery_failure": False,
            "clock_offset_hours": 0.0,
            "duplicate_webhook_replay": False,
            "corrupt_hmac_signature": False,
            "network_latency_ms": 0,
        })
        await store.record_customer_inbound_turn(phone_number_id, customer_phone)
        return {"status": "RESET_COMPLETE", "merchant_id": merchant_id}
