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
    def extract_phone_number_id(payload: Dict[str, Any], provider_slug: Optional[str] = None) -> Optional[str]:
        """Extracts external WhatsApp phone_number_id or routing key from provider webhook payload."""
        from app.adapters.whatsapp import get_whatsapp_bsp_adapter
        adapter = get_whatsapp_bsp_adapter(provider_slug=provider_slug)
        return adapter.extract_phone_number_id(payload)

    @staticmethod
    def normalize_inbound_payload(payload: Dict[str, Any], provider_slug: Optional[str] = None):
        """Normalizes any registered provider webhook payload into a NormalizedInboundEnvelope (ADR-0047)."""
        from app.adapters.whatsapp import get_whatsapp_bsp_adapter
        adapter = get_whatsapp_bsp_adapter(provider_slug=provider_slug)
        return adapter.normalize_inbound_webhook(payload)

    @staticmethod
    def unpack_inbound_payload(payload: Dict[str, Any], provider_slug: Optional[str] = None) -> Dict[str, Any]:
        """
        Unpacks nested provider webhook structures (Meta Cloud API, Termii, Twilio, 360dialog, Local Sandbox)
        into a unified provider-agnostic dictionary representation.
        """
        envelope = IngressService.normalize_inbound_payload(payload, provider_slug=provider_slug)
        return envelope.to_legacy_dict()

    @staticmethod
    def unpack_meta_payload(payload: Dict[str, Any], provider_slug: Optional[str] = None) -> Dict[str, Any]:
        """Backwards-compatible alias delegating to provider-agnostic unpack_inbound_payload."""
        return IngressService.unpack_inbound_payload(payload, provider_slug=provider_slug)



    @staticmethod
    async def get_or_create_conversation(
        session: AsyncSession,
        merchant_id: UUID,
        customer_phone: str,
        customer_name: Optional[str] = None,
        channel_id: Optional[UUID] = None,
    ) -> Conversation:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        query = await session.execute(
            select(Conversation)
            .where(
                Conversation.merchant_id == merchant_id,
                Conversation.customer_phone == customer_phone,
            )
            .order_by(desc(Conversation.updated_at))
            .limit(1)
        )
        conversation = query.scalar_one_or_none()
        if not conversation:
            conversation = Conversation(
                merchant_id=merchant_id,
                channel_id=channel_id,
                customer_phone=customer_phone,
                customer_name=customer_name or "Valued SME Customer",
                funnel_stage="discovery",
                lead_tier="WARM",
                lead_score=50,
            )
            session.add(conversation)
            await session.flush()
        else:
            # Returning customer outside 24h window: reset funnel session & update timestamp
            if conversation.updated_at < cutoff:
                conversation.funnel_stage = "discovery"
                conversation.is_open = True
            if customer_name and conversation.customer_name != customer_name:
                conversation.customer_name = customer_name
            if channel_id is not None and conversation.channel_id != channel_id:
                conversation.channel_id = channel_id
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
        skip_enqueue: bool = False,
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

        if skip_enqueue:
            job_id = f"inline-job-{webhook_event.id}"
        else:
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
        Pre-queries merchant FAQs/policies and persistent customer orders from PostgreSQL into dedicated slices.
        """
        from app.contexts.knowledge.services import KnowledgeService
        from app.core.generation.order_ledger import CustomerOrderLedger

        sanitized_text = sanitize_pii_quick(request.message)

        # Pre-query FAQs and persistent customer orders for grounded context
        faq_entries = await KnowledgeService.list_entries(
            session=session,
            merchant_id=merchant_id,
            entry_type=None,
            include_global=True,
        )
        faq_items = [e for e in faq_entries if e.entry_type in ("FAQ", "POLICY")]
        faq_manifest_lines = [f"- **{e.title}**: {e.content}" for e in faq_items]
        faq_manifest = "### Merchant Policies & FAQs:\n" + "\n".join(faq_manifest_lines) if faq_manifest_lines else None
        faq_data = [{"title": e.title, "content": e.content, "intent": (e.metadata_json or {}).get("intent")} for e in faq_items]

        recent_orders = await CustomerOrderLedger.list_recent(
            merchant_id=str(merchant_id),
            customer_phone=request.customer_phone,
            session=session,
        )
        order_lines = [
            f"- Order: {o.order_summary} | Destination: {o.delivery_zone or 'N/A'} | Total: ₦{o.total_kobo // 100:,} | Type: {o.fulfillment_type}"
            for o in recent_orders
        ]
        orders_manifest = "### Customer's Recent Orders:\n" + "\n".join(order_lines) if order_lines else None
        orders_data = [o.model_dump() for o in recent_orders]

        response = await CascadingNLUPipeline.process(
            text=sanitized_text,
            customer_phone=request.customer_phone,
            customer_name=request.customer_name or "Valued SME Customer",
            previous_context=request.previous_context,
            policy=request.policy,
            faq_manifest=faq_manifest,
            customer_orders_manifest=orders_manifest,
            faq_data=faq_data,
            customer_orders_data=orders_data,
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
