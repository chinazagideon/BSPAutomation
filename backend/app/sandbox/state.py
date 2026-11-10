"""Shared Redis & In-Memory State Store for the Local BSP Sandbox (ADR-0047).

Synchronizes Customer Service Window Governor, Sandbox Fault Injection Profile,
NLU Stage State Controllers, and real-time SSE event streams across `bsp_api` and `bsp_worker`.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import register_telemetry_sink
from app.sandbox.schemas import SandboxTelemetryRecord


class SandboxFaultProfile(BaseModel):
    """Runtime fault and protocol chaos flags shared between API and Worker."""
    force_rate_limit_429: bool = False
    force_upstream_500: bool = False
    simulate_delivery_failure: bool = False
    enforce_24h_window: bool = True
    clock_offset_hours: float = 0.0
    duplicate_webhook_replay: bool = False
    corrupt_hmac_signature: bool = False
    network_latency_ms: int = 0


class SandboxNLUController(BaseModel):
    """Runtime NLU stage state controllers shared between API and Worker."""
    use_fast_path: bool = True
    fast_path_confidence_threshold: float = 0.90
    use_custom_model: bool = True
    custom_model_confidence_threshold: float = 0.75
    use_llm_escalation: bool = True
    active_bsp_provider: str = "META_CLOUD"


class SandboxMessageRecord(BaseModel):
    """Rich WhatsApp message record stored in the Local BSP Sandbox."""
    id: str
    sender: str  # "user" | "bot" | "agent" | "system"
    to_phone: str
    from_phone: str
    phone_number_id: str
    merchant_id: Optional[str] = None
    text: str
    timestamp: str
    created_at_epoch: float = Field(default_factory=time.time)
    status: str = "delivered"  # "sent" | "delivered" | "read" | "failed"
    interactive_type: Optional[str] = None  # "buttons" | "list" | "carousel" | "template" | "media" | "payment_link" | "voice_note"
    header_text: Optional[str] = None
    button_title: Optional[str] = None
    buttons: List[Dict[str, Any]] = Field(default_factory=list)
    list_sections: List[Dict[str, Any]] = Field(default_factory=list)
    carousel_cards: List[Dict[str, Any]] = Field(default_factory=list)
    media: Optional[Dict[str, Any]] = None
    template: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# Process-local fallback state when Redis is unavailable (e.g. unit tests)
_IN_MEMORY_MESSAGES: List[Dict[str, Any]] = []
_IN_MEMORY_WEBHOOK_LOGS: List[Dict[str, Any]] = []
_IN_MEMORY_NLU_TRACES: List[Dict[str, Any]] = []
_IN_MEMORY_TELEMETRY_EVENTS: List[Dict[str, Any]] = []
_IN_MEMORY_WINDOW_MAP: Dict[str, float] = {}
_IN_MEMORY_FAULT_PROFILE = SandboxFaultProfile()
_IN_MEMORY_NLU_CONTROLLER = SandboxNLUController(
    use_fast_path=settings.USE_FAST_PATH,
    fast_path_confidence_threshold=settings.FAST_PATH_CONFIDENCE_THRESHOLD,
    use_custom_model=settings.USE_CUSTOM_MODEL,
    custom_model_confidence_threshold=settings.CUSTOM_MODEL_CONFIDENCE_THRESHOLD,
    use_llm_escalation=settings.USE_LLM_ESCALATION,
    active_bsp_provider=settings.WHATSAPP_BSP_PROVIDER,
)
_IN_MEMORY_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "order_payment_reminder_ng",
        "language": "en",
        "category": "UTILITY",
        "status": "APPROVED",
        "body": "Hello {{1}}, your order hold for {{2}} (₦{{3}}) expires in 5 minutes. Complete transfer to Moniepoint {{4}}.",
    },
    {
        "name": "re_engagement_window_opener",
        "language": "en",
        "category": "MARKETING",
        "status": "APPROVED",
        "body": "How far {{1}}! Fresh stock just land for {{2}}. Reply YES to view today's wholesale catalog prices.",
    },
    {
        "name": "nepa_hub_delay_notice",
        "language": "en",
        "category": "UTILITY",
        "status": "APPROVED",
        "body": "Notice: Our {{1}} support desk is switching to inverter backup. Your queue spot #{{2}} is safe!",
    },
]
_SSE_SUBSCRIBERS: List[asyncio.Queue] = []


class SandboxStateStore:
    """Manages cross-process Redis + In-Memory state for the Local BSP Sandbox."""

    REDIS_FAULT_KEY = "sandbox:fault_profile"
    REDIS_NLU_KEY = "sandbox:nlu_controller"
    REDIS_MESSAGES_KEY = "sandbox:messages"
    REDIS_WEBHOOKS_KEY = "sandbox:webhook_logs"
    REDIS_NLU_TRACES_KEY = "sandbox:nlu_traces"
    REDIS_TELEMETRY_KEY = "sandbox:telemetry_events"
    REDIS_WINDOW_PREFIX = "sandbox:window_24h:"
    REDIS_EVENTS_CHANNEL = "sandbox:events_stream"

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=0.5)
            await client.ping()
            self._redis = client
            return self._redis
        except Exception:
            return None

    def subscribe_sse(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        _SSE_SUBSCRIBERS.append(q)
        return q

    def unsubscribe_sse(self, q: asyncio.Queue) -> None:
        if q in _SSE_SUBSCRIBERS:
            _SSE_SUBSCRIBERS.remove(q)

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcasts a sandbox event to in-process SSE queues and Redis Pub/Sub."""
        envelope = {
            "id": f"evt-{uuid.uuid4().hex[:10]}",
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        for q in list(_SSE_SUBSCRIBERS):
            try:
                q.put_nowait(envelope)
            except asyncio.QueueFull:
                pass

        r = await self._get_redis()
        if r:
            try:
                await r.publish(self.REDIS_EVENTS_CHANNEL, json.dumps(envelope))
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Fault Injection Profile
    # -------------------------------------------------------------------------
    async def get_fault_profile(self) -> SandboxFaultProfile:
        global _IN_MEMORY_FAULT_PROFILE
        r = await self._get_redis()
        if r:
            try:
                raw = await r.get(self.REDIS_FAULT_KEY)
                if raw:
                    _IN_MEMORY_FAULT_PROFILE = SandboxFaultProfile(**json.loads(raw))
                    return _IN_MEMORY_FAULT_PROFILE
            except Exception:
                pass
        return _IN_MEMORY_FAULT_PROFILE

    async def update_fault_profile(self, updates: Dict[str, Any]) -> SandboxFaultProfile:
        global _IN_MEMORY_FAULT_PROFILE
        current = await self.get_fault_profile()
        merged = current.model_dump()
        merged.update({k: v for k, v in updates.items() if k in merged})
        _IN_MEMORY_FAULT_PROFILE = SandboxFaultProfile(**merged)
        r = await self._get_redis()
        if r:
            try:
                await r.set(self.REDIS_FAULT_KEY, _IN_MEMORY_FAULT_PROFILE.model_dump_json())
            except Exception:
                pass
        await self.broadcast_event("fault_profile_updated", _IN_MEMORY_FAULT_PROFILE.model_dump())
        return _IN_MEMORY_FAULT_PROFILE

    # -------------------------------------------------------------------------
    # Runtime NLU Stage Controller
    # -------------------------------------------------------------------------
    async def get_nlu_controller(self) -> SandboxNLUController:
        global _IN_MEMORY_NLU_CONTROLLER
        r = await self._get_redis()
        if r:
            try:
                raw = await r.get(self.REDIS_NLU_KEY)
                if raw:
                    _IN_MEMORY_NLU_CONTROLLER = SandboxNLUController(**json.loads(raw))
                    self._apply_nlu_settings(_IN_MEMORY_NLU_CONTROLLER)
                    return _IN_MEMORY_NLU_CONTROLLER
            except Exception:
                pass
        return _IN_MEMORY_NLU_CONTROLLER

    async def update_nlu_controller(self, updates: Dict[str, Any]) -> SandboxNLUController:
        global _IN_MEMORY_NLU_CONTROLLER
        current = await self.get_nlu_controller()
        merged = current.model_dump()
        merged.update({k: v for k, v in updates.items() if k in merged})
        _IN_MEMORY_NLU_CONTROLLER = SandboxNLUController(**merged)
        self._apply_nlu_settings(_IN_MEMORY_NLU_CONTROLLER)
        r = await self._get_redis()
        if r:
            try:
                await r.set(self.REDIS_NLU_KEY, _IN_MEMORY_NLU_CONTROLLER.model_dump_json())
            except Exception:
                pass
        await self.broadcast_event("nlu_controller_updated", _IN_MEMORY_NLU_CONTROLLER.model_dump())
        return _IN_MEMORY_NLU_CONTROLLER

    @staticmethod
    def _apply_nlu_settings(ctrl: SandboxNLUController) -> None:
        """Applies runtime controller flags to in-process settings."""
        settings.USE_FAST_PATH = ctrl.use_fast_path
        settings.FAST_PATH_CONFIDENCE_THRESHOLD = ctrl.fast_path_confidence_threshold
        settings.USE_CUSTOM_MODEL = ctrl.use_custom_model
        settings.CUSTOM_MODEL_CONFIDENCE_THRESHOLD = ctrl.custom_model_confidence_threshold
        settings.USE_LLM_ESCALATION = ctrl.use_llm_escalation

    # -------------------------------------------------------------------------
    # Customer Service Window Governor (24h Session Rule)
    # -------------------------------------------------------------------------
    async def record_customer_inbound_turn(self, phone_number_id: str, customer_phone: str) -> float:
        """Marks or refreshes the 24-hour customer service window upon customer inbound message."""
        now = time.time()
        clean_phone = customer_phone.lstrip("+")
        key = f"{phone_number_id}:{clean_phone}"
        _IN_MEMORY_WINDOW_MAP[key] = now
        r = await self._get_redis()
        if r:
            try:
                await r.set(f"{self.REDIS_WINDOW_PREFIX}{key}", str(now), ex=172800)
            except Exception:
                pass
        return now

    async def check_customer_service_window(self, phone_number_id: str, customer_phone: str) -> Dict[str, Any]:
        """Evaluates whether the 24-hour customer service window is open, accounting for clock_offset_hours."""
        faults = await self.get_fault_profile()
        clean_phone = customer_phone.lstrip("+")
        key = f"{phone_number_id}:{clean_phone}"
        last_inbound = _IN_MEMORY_WINDOW_MAP.get(key)

        r = await self._get_redis()
        if r:
            try:
                val = await r.get(f"{self.REDIS_WINDOW_PREFIX}{key}")
                if val:
                    last_inbound = float(val)
                    _IN_MEMORY_WINDOW_MAP[key] = last_inbound
            except Exception:
                pass

        effective_now = time.time() + (faults.clock_offset_hours * 3600.0)
        if last_inbound is None:
            # Default open in dev unless clock offset was explicitly pushed past 24h
            last_inbound = time.time()

        elapsed_seconds = max(0.0, effective_now - last_inbound)
        remaining_seconds = max(0.0, (24.0 * 3600.0) - elapsed_seconds)
        is_open = (not faults.enforce_24h_window) or (remaining_seconds > 0)

        return {
            "is_open": is_open,
            "elapsed_hours": round(elapsed_seconds / 3600.0, 2),
            "remaining_seconds": int(remaining_seconds),
            "remaining_hours": round(remaining_seconds / 3600.0, 2),
            "clock_offset_hours": faults.clock_offset_hours,
            "enforce_24h_window": faults.enforce_24h_window,
        }

    # -------------------------------------------------------------------------
    # Message, Webhook, and Telemetry History
    # -------------------------------------------------------------------------
    async def append_message(self, msg: SandboxMessageRecord) -> Dict[str, Any]:
        payload = msg.model_dump()
        _IN_MEMORY_MESSAGES.append(payload)
        if len(_IN_MEMORY_MESSAGES) > 200:
            del _IN_MEMORY_MESSAGES[:-200]

        r = await self._get_redis()
        if r:
            try:
                await r.rpush(self.REDIS_MESSAGES_KEY, json.dumps(payload))
                await r.ltrim(self.REDIS_MESSAGES_KEY, -200, -1)
            except Exception:
                pass

        await self.broadcast_event("whatsapp_message", payload)
        return payload

    async def get_messages(self, phone_number_id: Optional[str] = None) -> List[Dict[str, Any]]:
        r = await self._get_redis()
        items: List[Dict[str, Any]] = []
        if r:
            try:
                raw_list = await r.lrange(self.REDIS_MESSAGES_KEY, 0, -1)
                items = [json.loads(x) for x in raw_list]
            except Exception:
                items = list(_IN_MEMORY_MESSAGES)
        else:
            items = list(_IN_MEMORY_MESSAGES)

        if phone_number_id:
            items = [m for m in items if m.get("phone_number_id") == phone_number_id or not m.get("phone_number_id")]
        return items

    async def append_webhook_log(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        _IN_MEMORY_WEBHOOK_LOGS.insert(0, log_entry)
        if len(_IN_MEMORY_WEBHOOK_LOGS) > 100:
            del _IN_MEMORY_WEBHOOK_LOGS[100:]

        r = await self._get_redis()
        if r:
            try:
                await r.lpush(self.REDIS_WEBHOOKS_KEY, json.dumps(log_entry))
                await r.ltrim(self.REDIS_WEBHOOKS_KEY, 0, 99)
            except Exception:
                pass

        await self.broadcast_event("webhook_log", log_entry)
        return log_entry

    async def get_webhook_logs(self) -> List[Dict[str, Any]]:
        r = await self._get_redis()
        if r:
            try:
                raw_list = await r.lrange(self.REDIS_WEBHOOKS_KEY, 0, 50)
                if raw_list:
                    return [json.loads(x) for x in raw_list]
            except Exception:
                pass
        return list(_IN_MEMORY_WEBHOOK_LOGS[:50])

    async def append_nlu_trace(self, trace_entry: Dict[str, Any]) -> Dict[str, Any]:
        _IN_MEMORY_NLU_TRACES.insert(0, trace_entry)
        if len(_IN_MEMORY_NLU_TRACES) > 100:
            del _IN_MEMORY_NLU_TRACES[100:]

        r = await self._get_redis()
        if r:
            try:
                await r.lpush(self.REDIS_NLU_TRACES_KEY, json.dumps(trace_entry))
                await r.ltrim(self.REDIS_NLU_TRACES_KEY, 0, 99)
            except Exception:
                pass

        await self.broadcast_event("nlu_trace", trace_entry)
        return trace_entry

    async def get_nlu_traces(self) -> List[Dict[str, Any]]:
        r = await self._get_redis()
        if r:
            try:
                raw_list = await r.lrange(self.REDIS_NLU_TRACES_KEY, 0, 50)
                if raw_list:
                    return [json.loads(x) for x in raw_list]
            except Exception:
                pass
        return list(_IN_MEMORY_NLU_TRACES[:50])

    # -------------------------------------------------------------------------
    # Structured Telemetry Events (structlog + OpenTelemetry correlations)
    # -------------------------------------------------------------------------
    def record_telemetry_event_sync(self, raw_event: Dict[str, Any]) -> None:
        """Synchronously called by structlog telemetry sink processor."""
        try:
            event_name = str(raw_event.get("event", "log"))
            # Normalize core fields
            rec = SandboxTelemetryRecord(
                id=f"tel-{uuid.uuid4().hex[:10]}",
                event=event_name,
                level=str(raw_event.get("level", "info")),
                timestamp=str(raw_event.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                trace_id=raw_event.get("trace_id"),
                span_id=raw_event.get("span_id"),
                merchant_id=raw_event.get("merchant_id"),
                latency_ms=raw_event.get("latency_ms"),
                stage=raw_event.get("stage"),
                intent=raw_event.get("intent"),
                confidence=raw_event.get("confidence"),
                action=raw_event.get("action"),
                model=raw_event.get("model"),
                tokens_consumed=raw_event.get("tokens_consumed"),
                error=raw_event.get("error"),
                attributes={
                    k: v for k, v in raw_event.items()
                    if k not in (
                        "event", "level", "timestamp", "trace_id", "span_id",
                        "merchant_id", "latency_ms", "stage", "intent",
                        "confidence", "action", "model", "tokens_consumed", "error"
                    )
                },
            )
            payload = rec.model_dump()
            _IN_MEMORY_TELEMETRY_EVENTS.insert(0, payload)
            if len(_IN_MEMORY_TELEMETRY_EVENTS) > 200:
                del _IN_MEMORY_TELEMETRY_EVENTS[200:]

            envelope = {
                "id": f"evt-{uuid.uuid4().hex[:10]}",
                "type": "telemetry_event",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": payload,
            }
            for q in list(_SSE_SUBSCRIBERS):
                try:
                    q.put_nowait(envelope)
                except asyncio.QueueFull:
                    pass

            # If an async event loop is running, schedule background Redis push
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(self._persist_telemetry_to_redis(payload, envelope))
            except RuntimeError:
                pass
        except Exception as exc:
            import sys
            print(f"[SandboxTelemetrySink] Error recording telemetry: {exc}", file=sys.stderr)

    async def _persist_telemetry_to_redis(self, payload: Dict[str, Any], envelope: Dict[str, Any]) -> None:
        r = await self._get_redis()
        if r:
            try:
                await r.lpush(self.REDIS_TELEMETRY_KEY, json.dumps(payload))
                await r.ltrim(self.REDIS_TELEMETRY_KEY, 0, 199)
                await r.publish(self.REDIS_EVENTS_CHANNEL, json.dumps(envelope))
            except Exception:
                pass

    async def get_telemetry_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        r = await self._get_redis()
        if r:
            try:
                raw_list = await r.lrange(self.REDIS_TELEMETRY_KEY, 0, limit - 1)
                if raw_list:
                    return [json.loads(x) for x in raw_list]
            except Exception:
                pass
        return list(_IN_MEMORY_TELEMETRY_EVENTS[:limit])

    async def clear_telemetry(self) -> None:
        global _IN_MEMORY_TELEMETRY_EVENTS
        _IN_MEMORY_TELEMETRY_EVENTS.clear()
        r = await self._get_redis()
        if r:
            try:
                await r.delete(self.REDIS_TELEMETRY_KEY)
            except Exception:
                pass
        await self.broadcast_event("telemetry_cleared", {})

    async def clear_conversation(self, merchant_id: Optional[str] = None, customer_phone: Optional[str] = None) -> None:
        global _IN_MEMORY_MESSAGES
        _IN_MEMORY_MESSAGES.clear()
        r = await self._get_redis()
        if r:
            try:
                await r.delete(self.REDIS_MESSAGES_KEY)
            except Exception:
                pass
        if merchant_id and customer_phone:
            from app.core.generation.negotiation import NegotiationFrameManager
            await NegotiationFrameManager.evict_frame(merchant_id, customer_phone)
        await self.broadcast_event("conversation_cleared", {"merchant_id": merchant_id, "customer_phone": customer_phone})

    def get_templates(self) -> List[Dict[str, Any]]:
        return list(_IN_MEMORY_TEMPLATES)


_SANDBOX_STORE_SINGLETON: Optional[SandboxStateStore] = None


def get_sandbox_store() -> SandboxStateStore:
    global _SANDBOX_STORE_SINGLETON
    if _SANDBOX_STORE_SINGLETON is None:
        _SANDBOX_STORE_SINGLETON = SandboxStateStore()
        # Register store telemetry hook into structlog pipeline
        register_telemetry_sink(_SANDBOX_STORE_SINGLETON.record_telemetry_event_sync)
    return _SANDBOX_STORE_SINGLETON
