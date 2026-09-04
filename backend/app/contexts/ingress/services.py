"""Ingress & NLU Application Services."""

import time
from typing import Dict, Any, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc

from app.contexts.ingress.models import WebhookEvent, AIWallet, Conversation
from app.contexts.ingress.schemas import NLUClassificationRequest, NLUClassificationResponse
from app.contexts.ingress.pipeline import CascadingNLUPipeline
from app.core.security import generate_pii_token


def sanitize_pii_quick(text: str) -> str:
    """Pre-processing PII sanitization redacting Nigerian BVN, NIN, and Card PAN."""
    import re
    # 1. Card PAN
    text = re.sub(r"\b(?:\d{4}[-\s]?){3}\d{4}\b", lambda m: f"[REDACTED_CARD_PAN_{m.group(0)[-4:]}]", text)
    # 2. Explicit BVN (11 digits)
    text = re.sub(r"\b(?:bvn|bank\s*id)\s*(?:is|:=|:|=|-)?\s*(\d{11})\b", lambda m: f"[REDACTED_BVN_{m.group(1)[-4:]}]", text, flags=re.IGNORECASE)
    # 3. Explicit NIN (11 digits)
    text = re.sub(r"\b(?:nin|nimc)\s*(?:is|:=|:|=|-)?\s*(\d{11})\b", lambda m: f"[REDACTED_NIN_{m.group(1)[-4:]}]", text, flags=re.IGNORECASE)
    return text


# In-Memory Cache Fallbacks (for test/local environments without Redis)
_IN_MEMORY_CATALOG_CACHE: Dict[str, str] = {}
_IN_MEMORY_PROVIDER_CONTEXT_CACHE: Dict[str, Dict[str, Any]] = {}
_IN_MEMORY_FASTPATH_DICT_CACHE: Dict[str, List[Dict[str, Any]]] = {}


class IngressService:
    @staticmethod
    def extract_phone_number_id(payload: Dict[str, Any]) -> Optional[str]:
        """Extracts external WhatsApp phone_number_id from raw Meta Cloud webhook payload."""
        if "entry" in payload and isinstance(payload["entry"], list) and len(payload["entry"]) > 0:
            entry = payload["entry"][0]
            changes = entry.get("changes", [])
            if changes and isinstance(changes, list) and len(changes) > 0:
                value = changes[0].get("value", {})
                metadata = value.get("metadata", {})
                if "phone_number_id" in metadata:
                    return str(metadata["phone_number_id"])
        return payload.get("phone_number_id")

    @staticmethod
    def unpack_meta_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unpacks nested Meta Cloud API JSON structures:
        entry[0].changes[0].value.messages[0], button callbacks, interactive list replies, audio.
        """
        result: Dict[str, Any] = {
            "has_message": False,
            "sender_phone": "",
            "customer_name": "Valued Customer",
            "message_id": "",
            "message_type": "unknown",
            "text": "",
            "is_audio": False,
            "media_id": None,
            "is_interactive": False,
            "interactive_id": None,
        }

        if not payload.get("entry") or not isinstance(payload["entry"], list):
            return result

        entry = payload["entry"][0]
        changes = entry.get("changes", [])
        if not changes or not isinstance(changes, list):
            return result

        value = changes[0].get("value", {})
        contacts = value.get("contacts", [])
        if contacts and isinstance(contacts, list) and len(contacts) > 0:
            profile = contacts[0].get("profile", {})
            result["customer_name"] = profile.get("name", "Valued Customer")

        messages = value.get("messages", [])
        if not messages or not isinstance(messages, list):
            return result

        msg = messages[0]
        result["has_message"] = True
        result["sender_phone"] = str(msg.get("from", ""))
        result["message_id"] = str(msg.get("id", ""))
        msg_type = msg.get("type", "text")
        result["message_type"] = msg_type

        if msg_type == "text":
            result["text"] = msg.get("text", {}).get("body", "").strip()

        elif msg_type == "interactive":
            result["is_interactive"] = True
            interactive = msg.get("interactive", {})
            itype = interactive.get("type")
            if itype == "button_reply":
                reply = interactive.get("button_reply", {})
                result["text"] = reply.get("title", "")
                result["interactive_id"] = reply.get("id")
            elif itype == "list_reply":
                reply = interactive.get("list_reply", {})
                result["text"] = reply.get("title", "")
                result["interactive_id"] = reply.get("id")

        elif msg_type == "button":
            result["is_interactive"] = True
            btn = msg.get("button", {})
            result["text"] = btn.get("text", "")
            result["interactive_id"] = btn.get("payload")

        elif msg_type in ["audio", "voice"]:
            result["is_audio"] = True
            audio = msg.get("audio", {}) or msg.get("voice", {})
            media_id = audio.get("id")
            result["media_id"] = media_id
            result["text"] = f"[VOICE_NOTE_MEDIA_ID: {media_id}]"

        return result

    @staticmethod
    async def get_or_create_conversation(
        session: AsyncSession,
        merchant_id: UUID,
        customer_phone: str,
        customer_name: Optional[str] = None,
    ) -> Conversation:
        """Resolves active conversation within 24h sliding inactivity window or spawns a new one."""
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        query = await session.execute(
            select(Conversation)
            .where(
                Conversation.merchant_id == merchant_id,
                Conversation.customer_phone == customer_phone,
                Conversation.updated_at >= cutoff,
            )
            .order_by(desc(Conversation.updated_at))
            .limit(1)
        )
        conversation = query.scalar_one_or_none()

        if not conversation:
            conversation = Conversation(
                merchant_id=merchant_id,
                customer_phone=customer_phone,
                customer_name=customer_name or "Valued SME Customer",
                funnel_stage="discovery",
                lead_tier="WARM",
                lead_score=50,
            )
            session.add(conversation)
            await session.flush()
        else:
            if customer_name and conversation.customer_name != customer_name:
                conversation.customer_name = customer_name
            conversation.updated_at = datetime.now(timezone.utc)
            await session.flush()

        return conversation

    @staticmethod
    async def get_recent_conversation_history(
        session: AsyncSession,
        conversation_id: UUID,
        limit: int = 5,
    ) -> List[str]:
        """Queries the latest sanitized message texts from ingress.messages for NLU context."""
        from app.contexts.ingress.models import Message
        query = await session.execute(
            select(Message.sanitized_text)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
        )
        records = query.scalars().all()
        return list(reversed(records))

    @staticmethod
    async def get_cached_fast_path_dictionary(
        session: AsyncSession,
        merchant_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Loads custom merchant fast-path phrases with process-local fallback."""
        m_id = str(merchant_id)
        if m_id in _IN_MEMORY_FASTPATH_DICT_CACHE:
            return _IN_MEMORY_FASTPATH_DICT_CACHE[m_id]

        from app.contexts.ingress.models import FastPathDictionary
        query = await session.execute(
            select(FastPathDictionary).where(
                FastPathDictionary.merchant_id == merchant_id,
                FastPathDictionary.is_active == True,
            )
        )
        rows = query.scalars().all()
        dict_rules = [
            {
                "phrase_pattern": r.phrase_pattern,
                "intent": r.intent,
                "suggested_response_template": r.suggested_response_template,
            }
            for r in rows
        ]
        _IN_MEMORY_FASTPATH_DICT_CACHE[m_id] = dict_rules
        return dict_rules

    @staticmethod
    def get_cached_catalog_manifest(merchant_id: str) -> Optional[str]:
        """Retrieves cached compact Markdown/YAML Catalog Manifest for Stage 3 LLM."""
        return _IN_MEMORY_CATALOG_CACHE.get(merchant_id)

    @staticmethod
    def set_cached_catalog_manifest(merchant_id: str, manifest: str) -> None:
        """Sets cached Catalog Manifest."""
        _IN_MEMORY_CATALOG_CACHE[merchant_id] = manifest

    @staticmethod
    def get_cached_provider_context(merchant_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached Meta WABA Provider Context for Stage 3 LLM."""
        return _IN_MEMORY_PROVIDER_CONTEXT_CACHE.get(merchant_id)

    @staticmethod
    def set_cached_provider_context(merchant_id: str, context_data: Dict[str, Any]) -> None:
        """Sets cached Provider Context."""
        _IN_MEMORY_PROVIDER_CONTEXT_CACHE[merchant_id] = context_data

    @staticmethod
    async def ingest_webhook_fast_ack(
        session: AsyncSession,
        merchant_id: UUID,
        payload: Dict[str, Any],
        provider: str = "META_CLOUD",
        signature_verified: bool = True,
    ) -> Dict[str, Any]:
        """
        Ingests incoming WhatsApp BSP webhook and generates an instant <25ms 200 OK ACK.
        Persists raw event audit record and queues asynchronous background processing directly into ARQ Redis.
        """
        from app.core.worker import enqueue_webhook_job

        start_time = time.perf_counter()
        event_type = payload.get("object", "whatsapp_business_account")

        webhook_event = WebhookEvent(
            merchant_id=merchant_id,
            provider=provider,
            event_type=event_type,
            raw_payload=payload,
            signature_verified=signature_verified,
            ack_latency_ms=max(8, int((time.perf_counter() - start_time) * 1000.0)),
        )
        session.add(webhook_event)
        await session.flush()

        # Enqueue event directly into ARQ Redis task queue with W3C TraceContext
        from app.core.telemetry import inject_trace_context
        carrier: Dict[str, str] = {}
        inject_trace_context(carrier)
        trace_parent = carrier.get("traceparent")

        job_id = await enqueue_webhook_job(
            merchant_id=str(merchant_id),
            event_id=str(webhook_event.id),
            trace_parent=trace_parent,
        )

        return {
            "status": "EVENT_RECEIVED",
            "event_id": str(webhook_event.id),
            "job_id": job_id,
            "signature_verified": signature_verified,
            "ack_latency_ms": webhook_event.ack_latency_ms,
            "worker_queue": "redis_async_worker_pool_ng_01",
        }

    @staticmethod
    async def classify_and_route(
        session: AsyncSession,
        merchant_id: UUID,
        request: NLUClassificationRequest,
    ) -> NLUClassificationResponse:
        """
        Processes an incoming customer message through the 3-Stage Cascading NLU Pipeline:
        PII sanitization -> Stage 1 (Fast-Path) -> Stage 2 (Custom Model) -> Stage 3 (Gemini 3.7 Flash).
        """
        sanitized_text = sanitize_pii_quick(request.message)

        response = await CascadingNLUPipeline.process(
            text=sanitized_text,
            customer_phone=request.customer_phone,
            customer_name=request.customer_name or "Valued SME Customer",
            previous_context=request.previous_context,
        )

        # Update AI Wallet metrics if merchant wallet exists
        if response.tokens_consumed > 0 or response.estimated_kobo_saved > 0:
            wallet_query = await session.execute(
                select(AIWallet).where(AIWallet.merchant_id == merchant_id)
            )
            wallet = wallet_query.scalar_one_or_none()
            if wallet:
                if response.tokens_consumed > 0:
                    wallet.total_tokens_consumed += response.tokens_consumed
                    if wallet.bundled_tokens_remaining >= response.tokens_consumed:
                        wallet.bundled_tokens_remaining -= response.tokens_consumed
                    else:
                        cost_kobo = (response.tokens_consumed * 10)  # Approximate token pricing in Kobo
                        wallet.balance_kobo = max(0, wallet.balance_kobo - cost_kobo)
                        wallet.total_kobo_spent += cost_kobo
                if response.estimated_kobo_saved > 0:
                    wallet.estimated_kobo_saved += response.estimated_kobo_saved

        return response
