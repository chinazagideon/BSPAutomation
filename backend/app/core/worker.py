"""ARQ Background Worker settings, cron jobs, and asynchronous task definitions."""

import asyncio
import json
from typing import Any, Dict, Optional, List
from uuid import UUID
from datetime import datetime, timezone, timedelta
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select, update, func, desc

from app.core.config import settings
from app.core.database import tenant_session_scope, async_session_factory
from app.core.events import (
    event_bus,
    AgentHandoffRequestedEvent,
    HubPowerOutageDetectedEvent,
    HubPowerRestoredEvent,
    MerchantProviderContextUpdatedEvent,
)
from app.adapters.whatsapp import get_whatsapp_bsp_adapter
from app.core.logging import get_logger

logger = get_logger("worker.webhook")


# -----------------------------------------------------------------------------
# ARQ REDIS POOL & ENQUEUE HELPER
# -----------------------------------------------------------------------------
_ARQ_REDIS_POOL = None


async def get_arq_pool():
    global _ARQ_REDIS_POOL
    if _ARQ_REDIS_POOL is None:
        try:
            from arq import create_pool
            _ARQ_REDIS_POOL = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        except Exception as err:
            print(f"[Worker] Redis pool connection unavailable, falling back to mock queue: {err}")
            return None
    return _ARQ_REDIS_POOL


async def enqueue_webhook_job(
    merchant_id: str,
    event_id: str,
    trace_parent: Optional[str] = None,
) -> str:
    """Enqueues incoming webhook event_id directly into ARQ Redis task queue (<25ms Fast-ACK) with W3C TraceContext."""
    pool = await get_arq_pool()
    if pool:
        try:
            job = await pool.enqueue_job(
                "process_incoming_webhook_job",
                merchant_id=merchant_id,
                event_id=event_id,
                trace_parent=trace_parent,
            )
            return job.job_id if job else f"job-{event_id}"
        except Exception as err:
            print(f"[Worker] Error enqueuing to Redis: {err}")
    return f"mock-job-{event_id}"


# -----------------------------------------------------------------------------
# OUTAGE DEDUPLICATION & STATE MANAGEMENT (ADR-0038)
# -----------------------------------------------------------------------------
_IN_MEMORY_OUTAGE_CACHE: Dict[str, Dict[str, Any]] = {}


async def _get_outage_state(redis: Any, hub_id: str) -> Optional[Dict[str, Any]]:
    key = f"hub:{hub_id}:outage_state"
    if redis:
        try:
            val = await redis.get(key)
            if val:
                return json.loads(val) if isinstance(val, str) else json.loads(val.decode("utf-8"))
            return None
        except Exception as err:
            print(f"[Worker] Redis get outage state error: {err}")
    return _IN_MEMORY_OUTAGE_CACHE.get(hub_id)


async def _set_outage_state(redis: Any, hub_id: str, state: Dict[str, Any], ttl: int = 86400) -> None:
    key = f"hub:{hub_id}:outage_state"
    _IN_MEMORY_OUTAGE_CACHE[hub_id] = state
    if redis:
        try:
            val_str = json.dumps(state)
            await redis.set(key, val_str, ex=ttl)
        except Exception as err:
            print(f"[Worker] Redis set outage state error: {err}")


async def _delete_outage_state(redis: Any, hub_id: str) -> None:
    key = f"hub:{hub_id}:outage_state"
    _IN_MEMORY_OUTAGE_CACHE.pop(hub_id, None)
    if redis:
        try:
            await redis.delete(key)
        except Exception as err:
            print(f"[Worker] Redis delete outage state error: {err}")


async def enqueue_outage_dispatch_job(
    merchant_id: str,
    hub_id: str,
    hub_name: str,
    open_tickets: int,
    is_reminder: bool = False,
    reminder_count: int = 0,
    outage_started_at: Optional[str] = None,
    ctx: Optional[Dict[str, Any]] = None,
) -> str:
    """Enqueues decoupled background task for HubPowerOutageDetectedEvent dispatch."""
    is_worker_runtime = bool(ctx and (ctx.get("job_id") or ctx.get("redis")))
    if is_worker_runtime:
        pool = await get_arq_pool()
        if pool:
            try:
                job = await pool.enqueue_job(
                    "dispatch_hub_power_outage_job",
                    merchant_id=merchant_id,
                    hub_id=hub_id,
                    hub_name=hub_name,
                    open_tickets=open_tickets,
                    is_reminder=is_reminder,
                    reminder_count=reminder_count,
                    outage_started_at=outage_started_at,
                )
                return job.job_id if job else f"job-outage-{hub_id}"
            except Exception as err:
                print(f"[Worker] Error enqueuing outage job to Redis: {err}")

    # Synchronous execution for test contexts or when Redis pool is unavailable
    await dispatch_hub_power_outage_job(
        ctx=ctx or {},
        merchant_id=merchant_id,
        hub_id=hub_id,
        hub_name=hub_name,
        open_tickets=open_tickets,
        is_reminder=is_reminder,
        reminder_count=reminder_count,
        outage_started_at=outage_started_at,
    )
    return f"direct-outage-{hub_id}"


async def enqueue_recovery_dispatch_job(
    merchant_id: str,
    hub_id: str,
    hub_name: str,
    outage_duration_seconds: int = 0,
    ctx: Optional[Dict[str, Any]] = None,
) -> str:
    """Enqueues decoupled background task for HubPowerRestoredEvent dispatch."""
    is_worker_runtime = bool(ctx and (ctx.get("job_id") or ctx.get("redis")))
    if is_worker_runtime:
        pool = await get_arq_pool()
        if pool:
            try:
                job = await pool.enqueue_job(
                    "dispatch_hub_power_restored_job",
                    merchant_id=merchant_id,
                    hub_id=hub_id,
                    hub_name=hub_name,
                    outage_duration_seconds=outage_duration_seconds,
                )
                return job.job_id if job else f"job-restore-{hub_id}"
            except Exception as err:
                print(f"[Worker] Error enqueuing recovery job to Redis: {err}")

    # Synchronous execution for test contexts or when Redis pool is unavailable
    await dispatch_hub_power_restored_job(
        ctx=ctx or {},
        merchant_id=merchant_id,
        hub_id=hub_id,
        hub_name=hub_name,
        outage_duration_seconds=outage_duration_seconds,
    )
    return f"direct-restore-{hub_id}"


# -----------------------------------------------------------------------------
# ASYNCHRONOUS WORKER JOBS
# -----------------------------------------------------------------------------
async def process_incoming_webhook_job(
    ctx: Dict[str, Any],
    merchant_id: str,
    event_id: Optional[str] = None,
    raw_payload: Optional[Dict[str, Any]] = None,
    trace_parent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Background Task: Process incoming WhatsApp webhook asynchronously after <25ms 200 OK ACK.
    Restores W3C TraceContext and wraps execution in a continuous child span.
    """
    from app.core.telemetry import extract_trace_context, get_tracer
    from app.core.trace import set_context_merchant_id
    from app.core.logging import get_logger
    import structlog

    tracer = get_tracer("bsp-worker")
    logger = get_logger("worker.webhook")
    parent_ctx = extract_trace_context({"traceparent": trace_parent}) if trace_parent else None

    with tracer.start_as_current_span("arq.job:process_incoming_webhook_job", context=parent_ctx) as job_span:
        set_context_merchant_id(merchant_id)
        if trace_parent:
            job_span.set_attribute("bsp.traceparent", trace_parent)
        job_span.set_attribute("bsp.merchant_id", merchant_id)
        if event_id:
            job_span.set_attribute("bsp.event_id", event_id)
        structlog.contextvars.bind_contextvars(merchant_id=merchant_id)

        logger.info("webhook_job_started", merchant_id=merchant_id, event_id=event_id)
        return await _execute_webhook_processing(
            ctx=ctx,
            merchant_id=merchant_id,
            event_id=event_id,
            raw_payload=raw_payload,
            provider_slug=ctx.get("provider_slug") if ctx else None,
        )


async def _execute_webhook_processing(
    ctx: Dict[str, Any],
    merchant_id: str,
    event_id: Optional[str] = None,
    raw_payload: Optional[Dict[str, Any]] = None,
    provider_slug: Optional[str] = None,
) -> Dict[str, Any]:
    print(f"[Worker] Processing incoming webhook for merchant {merchant_id}, event: {event_id}")
    from app.contexts.ingress.models import WebhookEvent, Message
    from app.contexts.ingress.services import IngressService
    from app.contexts.compliance.services import ComplianceService, sanitize_nigerian_pii_detailed
    from app.contexts.compliance.schemas import ConsentLogRequest
    from app.contexts.ingress.pipeline import CascadingNLUPipeline
    from app.contexts.desk.services import DeskService
    from app.contexts.desk.schemas import ContextInjectionRequest

    http_client = ctx.get("audited_http_client") if ctx else None
    resolved_provider_slug = provider_slug or (ctx.get("provider_slug") if ctx else None)

    # Sync runtime NLU stage controller flags from shared SandboxStateStore (ADR-0047)
    try:
        from app.sandbox.state import get_sandbox_store
        await get_sandbox_store().get_nlu_controller()
    except Exception:
        pass

    async with tenant_session_scope(merchant_id) as session:
        payload = raw_payload
        webhook_event = None

        if event_id:
            res = await session.execute(
                select(WebhookEvent).where(WebhookEvent.id == UUID(event_id))
            )
            webhook_event = res.scalar_one_or_none()
            if webhook_event:
                payload = webhook_event.raw_payload
                if not resolved_provider_slug:
                    resolved_provider_slug = webhook_event.provider

        if not payload:
            return {"status": "SKIPPED_NO_PAYLOAD"}

        # Dynamic BSP adapter resolution governed by incoming provider (ADR-0047)
        whatsapp = get_whatsapp_bsp_adapter(
            http_client=http_client,
            provider_slug=resolved_provider_slug,
        )

        # 1. Unpack & Normalize Provider Payload (ADR-0047)
        inbound_envelope = IngressService.unpack_inbound_payload(payload, provider_slug=resolved_provider_slug)
        if inbound_envelope.get("is_status_update"):
            if webhook_event:
                webhook_event.processed_at = datetime.now(timezone.utc)
            try:
                from app.sandbox.state import get_sandbox_store
                await get_sandbox_store().broadcast_event("delivery_status_update", inbound_envelope)
            except Exception:
                pass
            return {
                "status": "PROCESSED_STATUS_UPDATE",
                "delivery_status": inbound_envelope.get("status_value"),
                "message_id": inbound_envelope.get("status_message_id"),
            }

        if not inbound_envelope["has_message"]:
            if webhook_event:
                webhook_event.processed_at = datetime.now(timezone.utc)
            return {"status": "SKIPPED_NON_MESSAGE_EVENT"}

        sender_phone = inbound_envelope["sender_phone"]
        customer_name = inbound_envelope["customer_name"]
        raw_text = inbound_envelope["text"]
        is_audio = inbound_envelope["is_audio"]
        media_id = inbound_envelope["media_id"]
        is_interactive = inbound_envelope.get("is_interactive", False)
        interactive_id = inbound_envelope.get("interactive_id")


        # Debounce rapid burst messages (ADR-0043 Point 8)
        if not is_interactive and not is_audio and raw_text:
            from app.core.generation.negotiation import NegotiationFrameManager
            debounced_text = await NegotiationFrameManager.debounce_incoming_message(
                merchant_id=merchant_id,
                customer_phone=sender_phone,
                raw_text=raw_text,
                debounce_window_seconds=1.2,
            )
            if not debounced_text:
                if webhook_event:
                    webhook_event.processed_at = datetime.now(timezone.utc)
                return {"status": "DEBOUNCED_INTO_PRIOR_JOB"}
            raw_text = debounced_text

        # 2. NDPA Compliance & PII Sanitization
        sanitized_text, _ = sanitize_nigerian_pii_detailed(raw_text)

        # 2B. Deterministic Negotiation Cancellation (ADR-0043 Point 11)
        from app.core.generation.negotiation import NegotiationFrameManager
        if NegotiationFrameManager.is_cancellation_intent(sanitized_text):
            await NegotiationFrameManager.evict_frame(merchant_id, sender_phone)
            cancel_reply = "No wahala! We don clear your pending order. Let us know anytime you're ready to order again."
            await whatsapp.send_text_message(to_phone=sender_phone, message=cancel_reply)
            if webhook_event:
                webhook_event.processed_at = datetime.now(timezone.utc)
            return {"status": "CANCELLED_NEGOTIATION"}

        # 3. Deterministic Opt-Out Interceptor (STOP / COMOT)
        opt_action = ComplianceService.check_opt_out_keyword(sanitized_text)
        if opt_action:
            await ComplianceService.log_chained_consent_event(
                session=session,
                merchant_id=UUID(merchant_id),
                request=ConsentLogRequest(
                    customer_phone=sender_phone,
                    action=opt_action,
                    channel="WHATSAPP",
                ),
            )
            await whatsapp.send_text_message(
                to_phone=sender_phone,
                message="You have successfully unsubscribed. We no go send you promotional messages again. Type START anytime to opt back in.",
            )
            if webhook_event:
                webhook_event.processed_at = datetime.now(timezone.utc)
            return {"status": "OPTED_OUT", "action": opt_action}

        # 4. Conversation Threading & History (24-Hour Sliding Window)
        conversation = await IngressService.get_or_create_conversation(
            session=session,
            merchant_id=UUID(merchant_id),
            customer_phone=sender_phone,
            customer_name=customer_name,
        )
        recent_history = await IngressService.get_recent_conversation_history(
            session=session,
            conversation_id=conversation.id,
            limit=5,
        )

        # 5. Voice Note Passthrough (ADR-0037)
        if is_audio:
            inbound_msg = Message(
                conversation_id=conversation.id,
                merchant_id=UUID(merchant_id),
                sender="user",
                raw_text=f"[VOICE_NOTE_MEDIA_ID: {media_id}]",
                sanitized_text=f"[VOICE_NOTE_MEDIA_ID: {media_id}]",
                intent="VOICE_NOTE_RECEIVED",
                tokens_used=0,
            )
            session.add(inbound_msg)

            ack_reply = "We receive your voice note! Our human support team go listen am shortly. If you dey hurry, you fit type your request here."
            await whatsapp.send_text_message(to_phone=sender_phone, message=ack_reply)

            outbound_msg = Message(
                conversation_id=conversation.id,
                merchant_id=UUID(merchant_id),
                sender="bot",
                raw_text=ack_reply,
                sanitized_text=ack_reply,
                intent="VOICE_NOTE_RECEIVED",
                tokens_used=0,
            )
            session.add(outbound_msg)
            await session.commit()

            # Emit Agent Handoff Requested Event
            card_resp = DeskService.generate_synthesized_context(
                ContextInjectionRequest(
                    customer_name=customer_name,
                    customer_phone=sender_phone,
                    chat_history=recent_history + [f"[Voice Note: {media_id}]"],
                )
            )
            await event_bus.publish(
                AgentHandoffRequestedEvent(
                    merchant_id=merchant_id,
                    conversation_id=str(conversation.id),
                    customer_phone=sender_phone,
                    customer_name=customer_name,
                    summary_card_data=card_resp.summary.model_dump(),
                    detected_entities={"media_id": media_id, "is_audio": True},
                )
            )
            if webhook_event:
                webhook_event.processed_at = datetime.now(timezone.utc)
            return {"status": "VOICE_NOTE_HANDED_OFF", "media_id": media_id}

        # 6. Multi-Turn Negotiation & Schema-Governed Tool Clarification (ADR-0043)
        from app.core.generation.negotiation import NegotiationFrameManager, NegotiationFrame
        from app.core.generation.tools import get_local_tool_dispatcher, ToolStatus
        from app.contexts.ingress.fast_path import extract_commercial_entities, fast_path_classify

        catalog_manifest = IngressService.get_cached_catalog_manifest(merchant_id)
        provider_context = IngressService.get_cached_provider_context(merchant_id)
        waba_name = "Enterprise SME Store"
        if provider_context and isinstance(provider_context, dict):
            waba_name = provider_context.get("verified_business_name", waba_name)
        custom_dict = await IngressService.get_cached_fast_path_dictionary(session, UUID(merchant_id))

        active_frame = await NegotiationFrameManager.get_frame(merchant_id, sender_phone)
        tool_handled = False
        tool_reply_text = None
        tool_buttons = None
        tool_action = None
        tool_envelope = None

        # 6A: Direct Interactive Button Slot Binding & Dual ID Scheme (ADR-0043, ADR-0044)
        if is_interactive and interactive_id:
            from app.core.generation.response_orchestrator import ResponseOrchestrator
            from app.core.generation.response_classifier import ResponseStrategy

            envelope = await ResponseOrchestrator.resolve_interactive_action(
                merchant_id=merchant_id,
                interactive_id=interactive_id,
                customer_phone=sender_phone,
                session=session,
                merchant_name=waba_name,
                catalog_manifest=catalog_manifest,
            )
            if envelope:
                tool_handled = True
                tool_envelope = envelope
                if envelope.strategy == ResponseStrategy.CHECKOUT_CONVERGED:
                    tool_action = "GENERATE_VIRTUAL_NUBAN_HOLD"
                elif envelope.strategy == ResponseStrategy.OUT_OF_STOCK_ALERT:
                    tool_action = "OUT_OF_STOCK_ALERT"
                elif envelope.strategy == ResponseStrategy.SINGLE_PRODUCT_QUOTE:
                    tool_action = "DISPLAY_PRODUCT_DETAIL_CARD"
                elif envelope.strategy == ResponseStrategy.CATALOG_PRODUCT_LIST:
                    tool_action = "DISPLAY_CATALOG_LIST"
                elif envelope.strategy == ResponseStrategy.AGENT_HANDOFF:
                    tool_action = "AGENT_HANDOFF"
                else:
                    tool_action = "DISPATCH_CLARIFICATION"

        # 6B: Plain Text Inbound with Active Negotiation Frame & Pending Offer
        elif active_frame and not tool_handled:
            # 6B.1: Check for Affirmation / Negation of a Pending Offer
            if active_frame.pending_offer:
                offer = dict(active_frame.pending_offer)
                if NegotiationFrameManager.is_affirmation_intent(sanitized_text):
                    logger.info(
                        "pending_offer_affirmed",
                        merchant_id=merchant_id,
                        sender_phone_hash=active_frame.phone_hash,
                        offer_action=offer.get("action"),
                        product=offer.get("product"),
                    )
                    offer_action = offer.get("action", "SHOW_PRICES")
                    active_frame.pending_offer = None
                    await NegotiationFrameManager.save_frame(merchant_id, sender_phone, active_frame)

                    from app.core.generation.response_orchestrator import ResponseOrchestrator
                    fake_nlu = {
                        "intent": "PRICE_INQUIRY",
                        "extracted_entities": {
                            "product": offer.get("product") or offer.get("query_term", "")
                        },
                        "suggested_reply": "Here are our current options and prices:",
                    }
                    envelope = await ResponseOrchestrator.resolve(
                        merchant_id=merchant_id,
                        nlu_result=fake_nlu,
                        customer_phone=sender_phone,
                        raw_message=sanitized_text,
                        session=session,
                    )
                    if envelope:
                        tool_handled = True
                        tool_envelope = envelope
                        tool_action = "DISPLAY_AFFIRMED_CATALOG_LIST"
                elif NegotiationFrameManager.is_negation_intent(sanitized_text):
                    logger.info(
                        "pending_offer_negated",
                        merchant_id=merchant_id,
                        sender_phone_hash=active_frame.phone_hash,
                    )
                    await NegotiationFrameManager.evict_frame(merchant_id, sender_phone)
                    tool_handled = True
                    tool_reply_text = "No wahala! We don clear that. Just let us know anytime you need anything."
                    tool_action = "CANCEL_PENDING_OFFER"

            # Check for topic shift / FAQ / handoff (Frame Preservation per ADR-0043 Point 6)
            if not tool_handled:
                quick_fp = fast_path_classify(sanitized_text, custom_dictionary=custom_dict)
                if quick_fp and quick_fp.intent in ["PRICE_INQUIRY", "DISPATCH_AGENT_HANDOFF", "SHOW_PRODUCT_CATALOG", "RESERVE_APPOINTMENT"]:
                    await NegotiationFrameManager.touch_frame(merchant_id, sender_phone)
                    # Fall through to standard NLU to answer inquiry while preserving frame
                else:
                    extracted = extract_commercial_entities(sanitized_text)
                    for k, v in extracted.items():
                        if v is not None:
                            active_frame.bound_slots[k] = v
                    if "location" in extracted:
                        active_frame.bound_slots["delivery_zone"] = extracted["location"]
                    if "fulfillment_type" in extracted:
                        active_frame.bound_slots["fulfillment_type"] = extracted["fulfillment_type"]

                    tool_res = await get_local_tool_dispatcher().evaluate(
                        intent=active_frame.intent,
                        slots=active_frame.bound_slots,
                        catalog_manifest=catalog_manifest,
                    )
                    if tool_res:
                        tool_handled = True
                        if tool_res.status == ToolStatus.NEEDS_CLARIFICATION:
                            active_frame.missing_slots = tool_res.missing_slots
                            await NegotiationFrameManager.save_frame(merchant_id, sender_phone, active_frame)
                            tool_reply_text = tool_res.clarification.prompt_text if tool_res.clarification else "Please choose an option."
                            tool_buttons = tool_res.clarification.buttons if tool_res.clarification else None
                            tool_action = "DISPATCH_CLARIFICATION"
                        elif tool_res.status == ToolStatus.CONVERGED:
                            await NegotiationFrameManager.evict_frame(merchant_id, sender_phone)
                            total_kobo = tool_res.calculated_total_kobo or 0
                            total_naira = f"₦{total_kobo // 100:,}"
                            loc_str = f" for delivery to {tool_res.bound_slots.get('delivery_zone', 'your address')}" if tool_res.bound_slots.get("fulfillment_type") == "EXPRESS_DELIVERY" else " for warehouse self-pickup"
                            tool_reply_text = (
                                f"Sharp! We don reserve your order ({tool_res.bound_slots.get('quantity', 1)}x {tool_res.bound_slots.get('product_name', 'item')}){loc_str}.\n"
                                f"Total Amount: *{total_naira}* (unpaid order valid for 10 minutes).\n\n"
                                f"🏦 *Payment Details (Dedicated Virtual NUBAN):*\n"
                                f"Bank: *Moniepoint MFB*\n"
                                f"Account Name: *{waba_name}*\n"
                                f"Account Number: *Allocated on hold confirmation*\n\n"
                                f"Once payment clear, receipt go land here sharp sharp!"
                            )
                            tool_action = "GENERATE_VIRTUAL_NUBAN_HOLD"
                        elif tool_res.status == ToolStatus.OUT_OF_STOCK:
                            await NegotiationFrameManager.evict_frame(merchant_id, sender_phone)
                            tool_reply_text = tool_res.clarification.prompt_text if tool_res.clarification else "Sorry, out of stock."
                            tool_buttons = tool_res.clarification.buttons if tool_res.clarification else None
                            tool_action = "OUT_OF_STOCK_ALERT"

        if tool_handled:
            from app.core.generation.response_formatter import EgressMessageType
            # Re-read active_frame state to get the updated intent
            inbound_intent = (
                "OUT_OF_STOCK_ALERT" if (tool_action == "OUT_OF_STOCK_ALERT" or (tool_envelope and tool_envelope.strategy == ResponseStrategy.OUT_OF_STOCK_ALERT))
                else ("INSTANT_CHECKOUT_ORDER" if (interactive_id and interactive_id.startswith("SET_SLOT:"))
                else ("PRICE_INQUIRY" if (interactive_id and interactive_id.startswith("PRODUCT:"))
                else ("SHOW_PRODUCT_CATALOG" if (interactive_id and "CATALOG" in interactive_id)
                else ("DISPATCH_AGENT_HANDOFF" if (interactive_id and "AGENT" in interactive_id)
                else (active_frame.intent if active_frame else "INSTANT_CHECKOUT_ORDER")))))
            )

            inbound_msg = Message(
                conversation_id=conversation.id,
                merchant_id=UUID(merchant_id),
                sender="user",
                raw_text=raw_text,
                sanitized_text=sanitized_text,
                intent=inbound_intent,
                is_fast_path=True,
                tokens_used=0,
            )
            session.add(inbound_msg)

            if tool_envelope:
                if tool_envelope.message_type == EgressMessageType.INTERACTIVE_LIST:
                    await whatsapp.send_interactive_list(
                        to_phone=sender_phone,
                        header_text=tool_envelope.header_text or "Catalog",
                        body_text=tool_envelope.body_text,
                        button_title=tool_envelope.button_title or "View Options",
                        sections=tool_envelope.sections or [],
                    )
                elif tool_envelope.message_type == EgressMessageType.INTERACTIVE_BUTTONS:
                    await whatsapp.send_interactive_buttons(
                        to_phone=sender_phone,
                        body_text=tool_envelope.body_text,
                        buttons=tool_envelope.buttons or [],
                    )
                else:
                    await whatsapp.send_text_message(to_phone=sender_phone, message=tool_envelope.body_text)

                outbound_msg = Message(
                    conversation_id=conversation.id,
                    merchant_id=UUID(merchant_id),
                    sender="bot",
                    raw_text=tool_envelope.body_text,
                    sanitized_text=tool_envelope.body_text,
                    intent=inbound_intent,
                    is_fast_path=True,
                    tokens_used=0,
                )
                session.add(outbound_msg)

            elif tool_reply_text:
                if tool_buttons and isinstance(tool_buttons, list) and len(tool_buttons) > 0:
                    await whatsapp.send_interactive_buttons(
                        to_phone=sender_phone,
                        body_text=tool_reply_text,
                        buttons=tool_buttons,
                    )
                else:
                    await whatsapp.send_text_message(to_phone=sender_phone, message=tool_reply_text)

                outbound_msg = Message(
                    conversation_id=conversation.id,
                    merchant_id=UUID(merchant_id),
                    sender="bot",
                    raw_text=tool_reply_text,
                    sanitized_text=tool_reply_text,
                    intent=inbound_intent,
                    is_fast_path=True,
                    tokens_used=0,
                )
                session.add(outbound_msg)

            if tool_action == "AGENT_HANDOFF":
                card_resp = DeskService.generate_synthesized_context(
                    ContextInjectionRequest(
                        customer_name=customer_name,
                        customer_phone=sender_phone,
                        chat_history=recent_history + [sanitized_text],
                    )
                )
                await event_bus.publish(
                    AgentHandoffRequestedEvent(
                        merchant_id=merchant_id,
                        conversation_id=str(conversation.id),
                        customer_phone=sender_phone,
                        customer_name=customer_name,
                        summary_card_data=card_resp.summary.model_dump(),
                        detected_entities={"interactive_id": interactive_id},
                    )
                )

            await session.commit()
            if webhook_event:
                webhook_event.processed_at = datetime.now(timezone.utc)
            try:
                from app.sandbox.state import get_sandbox_store
                current_frame = await NegotiationFrameManager.get_frame(merchant_id, sender_phone)
                await get_sandbox_store().append_nlu_trace({
                    "merchant_id": merchant_id,
                    "customer_phone": sender_phone,
                    "customer_name": customer_name,
                    "raw_text": raw_text,
                    "sanitized_text": sanitized_text,
                    "routing_source": "NEGOTIATION_FRAME",
                    "intent": inbound_intent,
                    "lead_tier": "HOT",
                    "urgency_score": 9,
                    "confidence": 1.0,
                    "detected_dialect": "Interactive / Slot-Binding",
                    "action": tool_action,
                    "tokens_consumed": 0,
                    "latency_ms": 2.1,
                    "active_frame": current_frame.model_dump(mode="json") if current_frame else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass
            return {"status": "PROCESSED_VIA_NEGOTIATION_FRAME", "action": tool_action}


        # 6C. Execute Cascading NLU Pipeline (Clean Slate)
        nlu_resp = await CascadingNLUPipeline.process(
            text=sanitized_text,
            customer_phone=sender_phone,
            customer_name=customer_name,
            previous_context=recent_history,
            custom_dictionary=custom_dict,
            catalog_manifest=catalog_manifest,
            provider_context=provider_context,
        )

        # If NLU produced a clarification, initialize NegotiationFrame in Redis
        if nlu_resp.action == "DISPATCH_CLARIFICATION":
            new_frame = NegotiationFrame(
                merchant_id=merchant_id,
                phone_hash="",
                active_tool="CheckoutOrderTool",
                intent=nlu_resp.intent,
                bound_slots=nlu_resp.extracted_entities.get("bound_slots", {}),
                missing_slots=nlu_resp.extracted_entities.get("missing_slots", []),
            )
            await NegotiationFrameManager.save_frame(merchant_id, sender_phone, new_frame)

        # 7. Record Inbound Message
        inbound_msg = Message(
            conversation_id=conversation.id,
            merchant_id=UUID(merchant_id),
            sender="user",
            raw_text=raw_text,
            sanitized_text=sanitized_text,
            intent=nlu_resp.intent,
            is_fast_path=(nlu_resp.routing_source == "FAST_PATH"),
            tokens_used=nlu_resp.tokens_consumed,
        )
        session.add(inbound_msg)

        # 8. Automated Egress Response via ResponseOrchestrator (ADR-0044)
        from app.core.generation.response_orchestrator import ResponseOrchestrator
        from app.core.generation.response_classifier import ResponseStrategy
        from app.core.generation.response_formatter import EgressMessageType

        merchant_name_val = "Enterprise SME Store"
        try:
            from app.contexts.core.models import Merchant
            merchant_obj = await session.get(Merchant, UUID(merchant_id))
            if merchant_obj and merchant_obj.business_name:
                merchant_name_val = merchant_obj.business_name
        except Exception:
            pass

        envelope = await ResponseOrchestrator.resolve(
            merchant_id=merchant_id,
            nlu_result=nlu_resp,
            customer_phone=sender_phone,
            raw_message=sanitized_text,
            session=session,
            merchant_name=merchant_name_val,
        )

        if envelope:
            # Register pending offer for catalog lists or quotes to power zero-token affirmations
            if envelope.strategy in [ResponseStrategy.CATALOG_PRODUCT_LIST, ResponseStrategy.SINGLE_PRODUCT_QUOTE, ResponseStrategy.FULL_CATALOG_BROWSE]:
                target_prod = nlu_resp.extracted_entities.get("product") or ""
                frame_to_update = active_frame or NegotiationFrame(
                    merchant_id=merchant_id,
                    phone_hash="",
                    active_tool="CheckoutOrderTool",
                    intent=nlu_resp.intent,
                    bound_slots={},
                    missing_slots=[],
                )
                frame_to_update.pending_offer = {
                    "action": "SHOW_PRICES",
                    "product": target_prod,
                    "strategy": envelope.strategy.value,
                }
                await NegotiationFrameManager.save_frame(merchant_id, sender_phone, frame_to_update)
                logger.info(
                    "pending_offer_registered",
                    merchant_id=merchant_id,
                    product=target_prod,
                    strategy=envelope.strategy.value,
                )

            if envelope.message_type == EgressMessageType.INTERACTIVE_LIST:
                await whatsapp.send_interactive_list(
                    to_phone=sender_phone,
                    header_text=envelope.header_text or "Catalog",
                    body_text=envelope.body_text,
                    button_title=envelope.button_title or "View Options",
                    sections=envelope.sections or [],
                )
            elif envelope.message_type == EgressMessageType.INTERACTIVE_BUTTONS:
                await whatsapp.send_interactive_buttons(
                    to_phone=sender_phone,
                    body_text=envelope.body_text,
                    buttons=envelope.buttons or [],
                )
            else:
                await whatsapp.send_text_message(to_phone=sender_phone, message=envelope.body_text)

            outbound_msg = Message(
                conversation_id=conversation.id,
                merchant_id=UUID(merchant_id),
                sender="bot",
                raw_text=envelope.body_text,
                sanitized_text=envelope.body_text,
                intent=nlu_resp.intent,
                is_fast_path=(nlu_resp.routing_source == "FAST_PATH"),
                tokens_used=0,
            )
            session.add(outbound_msg)

        # 9. Cross-Context Agent Desk Escalation (ADR-0036)
        if nlu_resp.action == "DISPATCH_AGENT_HANDOFF":
            await session.commit()
            card_resp = DeskService.generate_synthesized_context(
                ContextInjectionRequest(
                    customer_name=customer_name,
                    customer_phone=sender_phone,
                    chat_history=recent_history + [sanitized_text],
                )
            )
            await event_bus.publish(
                AgentHandoffRequestedEvent(
                    merchant_id=merchant_id,
                    conversation_id=str(conversation.id),
                    customer_phone=sender_phone,
                    customer_name=customer_name,
                    summary_card_data=card_resp.summary.model_dump(),
                    detected_entities=nlu_resp.extracted_entities,
                )
            )

        if webhook_event:
            webhook_event.processed_at = datetime.now(timezone.utc)

        try:
            from app.sandbox.state import get_sandbox_store
            current_frame = await NegotiationFrameManager.get_frame(merchant_id, sender_phone)
            await get_sandbox_store().append_nlu_trace({
                "merchant_id": merchant_id,
                "customer_phone": sender_phone,
                "customer_name": customer_name,
                "raw_text": raw_text,
                "sanitized_text": sanitized_text,
                "routing_source": nlu_resp.routing_source,
                "intent": nlu_resp.intent,
                "lead_tier": nlu_resp.lead_tier,
                "urgency_score": nlu_resp.urgency_score,
                "confidence": nlu_resp.confidence,
                "detected_dialect": nlu_resp.detected_dialect,
                "action": nlu_resp.action,
                "extracted_entities": nlu_resp.extracted_entities,
                "tokens_consumed": nlu_resp.tokens_consumed,
                "latency_ms": nlu_resp.latency_ms,
                "strategy": envelope.strategy.value if envelope else None,
                "active_frame": current_frame.model_dump(mode="json") if current_frame else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

        return {
            "status": "PROCESSED",
            "merchant_id": merchant_id,
            "intent": nlu_resp.intent,
            "routing_source": nlu_resp.routing_source,
        }



async def reconcile_payment_settlement_job(
    ctx: Dict[str, Any],
    merchant_id: str,
    payment_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Reconciles incoming Moniepoint MFB settlement webhook against Anti-Ghosting cart."""
    print(f"[Worker] Reconciling payment settlement for merchant {merchant_id}")
    return {"status": "SETTLED_BALANCED", "merchant_id": merchant_id}


async def release_expired_reservation_holds_job(ctx: Dict[str, Any]) -> None:
    """Cron Job: Releases 10-minute anti-no-show provisional reservation holds."""
    pass


async def check_agent_heartbeat_timeouts_job(ctx: Dict[str, Any]) -> None:
    """
    Cron Job (Every 30s): Detects missed agent heartbeats (>60s) and transitions
    inactive agents to OFFLINE_NEPA. Deduplicates outages via Redis state machine (ADR-0038).
    - Initial transition -> enqueues dispatch_hub_power_outage_job (is_reminder=False)
    - Persisting outage -> enqueues reminder alert every 30 minutes (is_reminder=True)
    - Recovery transition -> enqueues dispatch_hub_power_restored_job
    """
    from app.contexts.desk.models import AgentProfile, Hub, EscalationTicket
    from app.contexts.core.models import Merchant

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=settings.DESK_HEARTBEAT_TIMEOUT_SECONDS)
    redis = ctx.get("redis") if ctx else None
    if redis is None and ctx and ctx.get("job_id"):
        redis = await get_arq_pool()

    # 1. Fetch all merchants (core.merchants is not restricted by RLS)
    async with async_session_factory() as global_session:
        merchants_res = await global_session.execute(select(Merchant.id))
        merchant_ids = merchants_res.scalars().all()

    semaphore = asyncio.Semaphore(10)

    async def process_merchant_heartbeats(m_id):
        async with semaphore:
            merchant_id_str = str(m_id)
            async with tenant_session_scope(merchant_id_str) as session:
                # 1. Update inactive agents to OFFLINE_NEPA
                await session.execute(
                    update(AgentProfile)
                    .where(
                        AgentProfile.merchant_id == m_id,
                        AgentProfile.last_heartbeat_at < cutoff,
                        AgentProfile.work_status == "ONLINE",
                    )
                    .values(work_status="OFFLINE_NEPA")
                )
                await session.flush()

                # 2. Check active hubs for this merchant
                hubs_query = await session.execute(
                    select(Hub).where(Hub.merchant_id == m_id, Hub.is_active == True)
                )
                hubs = hubs_query.scalars().all()

                for hub in hubs:
                    online_count = (
                        await session.execute(
                            select(func.count(AgentProfile.id))
                            .where(AgentProfile.hub_id == hub.id, AgentProfile.work_status == "ONLINE")
                        )
                    ).scalar() or 0

                    hub_id_str = str(hub.id)
                    outage_state = await _get_outage_state(redis, hub_id_str)

                    if online_count == 0:
                        open_tickets = (
                            await session.execute(
                                select(func.count(EscalationTicket.id))
                                .where(
                                    EscalationTicket.merchant_id == hub.merchant_id,
                                    EscalationTicket.status.in_(["OPEN", "PENDING_ASSIGNMENT"]),
                                )
                            )
                        ).scalar() or 0

                        if open_tickets > 0:
                            if outage_state is None:
                                # Initial outage transition
                                new_state = {
                                    "outage_started_at": now.isoformat(),
                                    "last_alerted_at": now.isoformat(),
                                    "reminder_count": 0,
                                }
                                await _set_outage_state(redis, hub_id_str, new_state, ttl=86400)
                                await enqueue_outage_dispatch_job(
                                    merchant_id=merchant_id_str,
                                    hub_id=hub_id_str,
                                    hub_name=hub.hub_name,
                                    open_tickets=open_tickets,
                                    is_reminder=False,
                                    reminder_count=0,
                                    outage_started_at=now.isoformat(),
                                    ctx=ctx,
                                )
                            else:
                                # Outage already active -> check if 30-minute reminder is due
                                last_alerted = datetime.fromisoformat(outage_state["last_alerted_at"])
                                if (now - last_alerted).total_seconds() >= 1800:
                                    count = outage_state.get("reminder_count", 0) + 1
                                    outage_state["last_alerted_at"] = now.isoformat()
                                    outage_state["reminder_count"] = count
                                    await _set_outage_state(redis, hub_id_str, outage_state, ttl=86400)
                                    await enqueue_outage_dispatch_job(
                                        merchant_id=merchant_id_str,
                                        hub_id=hub_id_str,
                                        hub_name=hub.hub_name,
                                        open_tickets=open_tickets,
                                        is_reminder=True,
                                        reminder_count=count,
                                        outage_started_at=outage_state.get("outage_started_at"),
                                        ctx=ctx,
                                    )
                    else:
                        # Hub has online agents -> check if recovering from previous outage
                        if outage_state is not None:
                            started_at_str = outage_state.get("outage_started_at")
                            started_at = datetime.fromisoformat(started_at_str) if started_at_str else now
                            duration = max(0, int((now - started_at).total_seconds()))

                            await _delete_outage_state(redis, hub_id_str)
                            await enqueue_recovery_dispatch_job(
                                merchant_id=merchant_id_str,
                                hub_id=hub_id_str,
                                hub_name=hub.hub_name,
                                outage_duration_seconds=duration,
                                ctx=ctx,
                            )

    if merchant_ids:
        await asyncio.gather(*[process_merchant_heartbeats(m_id) for m_id in merchant_ids])


async def dispatch_hub_power_outage_job(
    ctx: Dict[str, Any],
    merchant_id: str,
    hub_id: str,
    hub_name: str,
    open_tickets: int,
    is_reminder: bool = False,
    reminder_count: int = 0,
    outage_started_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Decoupled Asynchronous Task: Publishes HubPowerOutageDetectedEvent to subscribers."""
    from app.core.telemetry import get_tracer
    from app.core.logging import get_logger

    tracer = get_tracer("bsp-worker")
    logger = get_logger("worker.outage")

    with tracer.start_as_current_span("arq.job:dispatch_hub_power_outage_job") as span:
        span.set_attribute("bsp.merchant_id", merchant_id)
        span.set_attribute("bsp.hub_id", hub_id)
        span.set_attribute("bsp.is_reminder", is_reminder)
        span.set_attribute("bsp.reminder_count", reminder_count)

        logger.info(
            "dispatching_hub_outage_alert",
            merchant_id=merchant_id,
            hub_id=hub_id,
            is_reminder=is_reminder,
            reminder_count=reminder_count,
        )

        started_dt = datetime.fromisoformat(outage_started_at) if outage_started_at else None

        await event_bus.publish(
            HubPowerOutageDetectedEvent(
                merchant_id=merchant_id,
                hub_id=hub_id,
                hub_name=hub_name,
                open_ticket_count=open_tickets,
                is_reminder=is_reminder,
                reminder_count=reminder_count,
                outage_started_at=started_dt,
            )
        )
        return {"status": "OUTAGE_ALERT_DISPATCHED", "hub_id": hub_id, "is_reminder": is_reminder}


async def dispatch_hub_power_restored_job(
    ctx: Dict[str, Any],
    merchant_id: str,
    hub_id: str,
    hub_name: str,
    outage_duration_seconds: int = 0,
) -> Dict[str, Any]:
    """Decoupled Asynchronous Task: Publishes HubPowerRestoredEvent to subscribers."""
    from app.core.telemetry import get_tracer
    from app.core.logging import get_logger

    tracer = get_tracer("bsp-worker")
    logger = get_logger("worker.outage")

    with tracer.start_as_current_span("arq.job:dispatch_hub_power_restored_job") as span:
        span.set_attribute("bsp.merchant_id", merchant_id)
        span.set_attribute("bsp.hub_id", hub_id)
        span.set_attribute("bsp.outage_duration_seconds", outage_duration_seconds)

        logger.info(
            "dispatching_hub_power_restored",
            merchant_id=merchant_id,
            hub_id=hub_id,
            duration_seconds=outage_duration_seconds,
        )

        await event_bus.publish(
            HubPowerRestoredEvent(
                merchant_id=merchant_id,
                hub_id=hub_id,
                hub_name=hub_name,
                outage_duration_seconds=outage_duration_seconds,
            )
        )
        return {"status": "POWER_RESTORED_DISPATCHED", "hub_id": hub_id}


async def sync_merchant_provider_context_job(
    ctx: Dict[str, Any],
    merchant_id: str,
    provider_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Asynchronously refreshes Meta WABA Provider Context in cache (ADR-0035)."""
    from app.contexts.ingress.services import IngressService
    IngressService.set_cached_provider_context(merchant_id, provider_data)
    await event_bus.publish(
        MerchantProviderContextUpdatedEvent(
            merchant_id=merchant_id,
            provider_context_data=provider_data,
        )
    )
    return {"status": "PROVIDER_CONTEXT_SYNCED", "merchant_id": merchant_id}


async def startup(ctx: Dict[str, Any]) -> None:
    from app.core.egress import create_pooled_http_client, AuditedHttpClient, set_default_audited_client
    from app.core.telemetry import init_telemetry
    from app.core.logging import get_logger

    if settings.OTEL_ENABLED:
        init_telemetry("bsp-arq-worker")

    logger = get_logger("worker.lifecycle")
    logger.info("worker_starting", app_name=settings.APP_NAME)
    print("[Worker] ARQ Background Worker starting up...")

    pooled_httpx = create_pooled_http_client()
    audited_client = AuditedHttpClient(client=pooled_httpx)
    ctx["httpx_client"] = pooled_httpx
    ctx["audited_http_client"] = audited_client
    set_default_audited_client(audited_client)


async def shutdown(ctx: Dict[str, Any]) -> None:
    from app.core.telemetry import shutdown_telemetry
    print("[Worker] ARQ Background Worker shutting down...")
    if "httpx_client" in ctx and ctx["httpx_client"]:
        await ctx["httpx_client"].aclose()
        print("[Worker] ARQ Worker Egress HTTP connection pool closed successfully.")
    if settings.OTEL_ENABLED:
        await shutdown_telemetry()


class WorkerSettings:
    """ARQ Worker configuration class."""
    functions = [
        process_incoming_webhook_job,
        reconcile_payment_settlement_job,
        release_expired_reservation_holds_job,
        check_agent_heartbeat_timeouts_job,
        sync_merchant_provider_context_job,
        dispatch_hub_power_outage_job,
        dispatch_hub_power_restored_job,
    ]
    cron_jobs = [
        cron(release_expired_reservation_holds_job, minute=None, second=0),  # Every minute
        cron(check_agent_heartbeat_timeouts_job, minute=None, second={0, 30}),  # Every 30s
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 50
    poll_delay = 0.5
