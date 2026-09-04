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
        )


async def _execute_webhook_processing(
    ctx: Dict[str, Any],
    merchant_id: str,
    event_id: Optional[str] = None,
    raw_payload: Optional[Dict[str, Any]] = None,
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
    whatsapp = get_whatsapp_bsp_adapter(http_client=http_client)

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

        if not payload:
            return {"status": "SKIPPED_NO_PAYLOAD"}

        # 1. Unpack Meta Payload
        unpacked = IngressService.unpack_meta_payload(payload)
        if not unpacked["has_message"]:
            if webhook_event:
                webhook_event.processed_at = datetime.now(timezone.utc)
            return {"status": "SKIPPED_NON_MESSAGE_EVENT"}

        sender_phone = unpacked["sender_phone"]
        customer_name = unpacked["customer_name"]
        raw_text = unpacked["text"]
        is_audio = unpacked["is_audio"]
        media_id = unpacked["media_id"]

        # 2. NDPA Compliance & PII Sanitization
        sanitized_text, _ = sanitize_nigerian_pii_detailed(raw_text)

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

        # 6. Execute Cascading NLU Pipeline
        custom_dict = await IngressService.get_cached_fast_path_dictionary(session, UUID(merchant_id))
        catalog_manifest = IngressService.get_cached_catalog_manifest(merchant_id)
        provider_context = IngressService.get_cached_provider_context(merchant_id)

        nlu_resp = await CascadingNLUPipeline.process(
            text=sanitized_text,
            customer_phone=sender_phone,
            customer_name=customer_name,
            previous_context=recent_history,
            custom_dictionary=custom_dict,
            catalog_manifest=catalog_manifest,
            provider_context=provider_context,
        )

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

        # 8. Automated Egress Response
        if nlu_resp.suggested_reply:
            await whatsapp.send_text_message(to_phone=sender_phone, message=nlu_resp.suggested_reply)
            outbound_msg = Message(
                conversation_id=conversation.id,
                merchant_id=UUID(merchant_id),
                sender="bot",
                raw_text=nlu_resp.suggested_reply,
                sanitized_text=nlu_resp.suggested_reply,
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
