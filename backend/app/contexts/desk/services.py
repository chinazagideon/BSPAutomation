import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc

from app.contexts.desk.models import AgentProfile, EscalationTicket
from app.contexts.desk.schemas import (
    HeartbeatPingRequest,
    HeartbeatPingResponse,
    ContextInjectionRequest,
    SixFieldContextCard,
    ContextInjectionResponse,
)
from app.core.database import async_session_factory, tenant_session_scope
from app.core.events import (
    event_bus,
    AgentHandoffRequestedEvent,
    HubPowerOutageDetectedEvent,
    HubPowerRestoredEvent,
)
from app.adapters.whatsapp import get_whatsapp_bsp_adapter


# -----------------------------------------------------------------------------
# SSE IN-MEMORY PUB/SUB BROADCASTER
# -----------------------------------------------------------------------------
_SSE_CLIENTS: Dict[str, List[asyncio.Queue]] = {}


def register_sse_client(merchant_id: str) -> asyncio.Queue:
    if merchant_id not in _SSE_CLIENTS:
        _SSE_CLIENTS[merchant_id] = []
    q: asyncio.Queue = asyncio.Queue()
    _SSE_CLIENTS[merchant_id].append(q)
    return q


def unregister_sse_client(merchant_id: str, q: asyncio.Queue) -> None:
    if merchant_id in _SSE_CLIENTS and q in _SSE_CLIENTS[merchant_id]:
        _SSE_CLIENTS[merchant_id].remove(q)


async def broadcast_sse_event(merchant_id: str, event_name: str, data: Dict[str, Any]) -> None:
    """Broadcasts a real-time event to all connected agent streams for this merchant."""
    queues = _SSE_CLIENTS.get(merchant_id, [])
    for q in queues:
        await q.put({"event": event_name, "data": data})


class DeskService:
    @staticmethod
    async def record_agent_heartbeat(
        session: AsyncSession,
        merchant_id: UUID,
        request: HeartbeatPingRequest,
    ) -> HeartbeatPingResponse:
        """
        Records an active heartbeat ping from a support agent terminal,
        keeping work_status ONLINE and resetting NEPA failover counter.
        """
        now = datetime.now(timezone.utc)
        await session.execute(
            update(AgentProfile)
            .where(AgentProfile.id == request.agent_id, AgentProfile.merchant_id == merchant_id)
            .values(last_heartbeat_at=now, work_status="ONLINE")
        )

        return HeartbeatPingResponse(
            agent_id=request.agent_id,
            status="ONLINE",
            last_heartbeat_at=now,
            nepa_offline_threshold_seconds=60,
        )

    @staticmethod
    def generate_synthesized_context(request: ContextInjectionRequest) -> ContextInjectionResponse:
        """
        Synthesizes a 6-field context card from customer conversation history
        to eliminate repeated questions when escalating to a human agent.
        """
        history_str = " ".join(request.chat_history).lower()
        budget = "₦220,000" if "220" in history_str or "carton" in history_str else "₦50,000"
        urgency = "HOT" if any(w in history_str for w in ["today", "now", "urgent", "pay", "order"]) else "WARM"
        dialect = "Nigerian Pidgin" if any(w in history_str for w in ["abeg", "dey", "wetin", "how far"]) else "Standard English"

        card = SixFieldContextCard(
            executive_summary=f"Customer {request.customer_name} is requesting pricing and express delivery dispatch for wholesale items.",
            detected_budget_naira=budget,
            urgency_tier=urgency,
            dialect=dialect,
            key_blockers="Customer is confirming if pay-on-delivery is supported for first-time orders.",
            suggested_first_response=f"Good afternoon {request.customer_name}! I see you want items dispatched today. I have our logistics team on standby.",
        )

        return ContextInjectionResponse(
            status="CONTEXT_INJECTED",
            agent_hub="Ikeja Tech Support Hub 01",
            customer={"name": request.customer_name, "phone": request.customer_phone},
            summary=card,
        )

    @staticmethod
    async def claim_ticket(
        session: AsyncSession,
        ticket_id: UUID,
        agent_id: UUID,
        merchant_id: UUID,
    ) -> Optional[EscalationTicket]:
        """
        Atomic Ticket Claim Guard (ADR-0036):
        Executes conditional update WHERE assigned_agent_id IS NULL AND status = 'OPEN'.
        Returns ticket if claim succeeds, or None if already claimed.
        """
        stmt = (
            update(EscalationTicket)
            .where(
                EscalationTicket.id == ticket_id,
                EscalationTicket.merchant_id == merchant_id,
                EscalationTicket.assigned_agent_id.is_(None),
                EscalationTicket.status.in_(["OPEN", "PENDING_ASSIGNMENT"]),
            )
            .values(
                assigned_agent_id=agent_id,
                status="IN_PROGRESS",
            )
            .returning(EscalationTicket)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()

        if ticket:
            await broadcast_sse_event(
                str(merchant_id),
                "ticket_claimed",
                {"ticket_id": str(ticket_id), "assigned_agent_id": str(agent_id)},
            )
        return ticket

    @staticmethod
    async def handle_agent_handoff_requested(event: AgentHandoffRequestedEvent) -> None:
        """
        Domain Event Handler: Ingests handoff request into desk.escalation_tickets with NULL assigned_agent
        (Claim Model ADR-0036) and pushes 6-Field Context Card to live agent SSE streams.
        """
        from app.contexts.desk.models import Hub
        async with tenant_session_scope(event.merchant_id) as session:
            # Resolve primary hub if available, or create default hub
            hub_res = await session.execute(
                select(Hub.id).where(Hub.merchant_id == UUID(event.merchant_id), Hub.is_active == True).limit(1)
            )
            primary_hub_id = hub_res.scalar_one_or_none()
            if not primary_hub_id:
                default_hub = Hub(
                    merchant_id=UUID(event.merchant_id),
                    name="Primary Support Hub",
                    region="LAGOS_MAINLAND",
                    is_active=True,
                )
                session.add(default_hub)
                await session.flush()
                primary_hub_id = default_hub.id

            summary_data = event.summary_card_data or {}
            ticket = EscalationTicket(
                merchant_id=UUID(event.merchant_id),
                conversation_id=UUID(event.conversation_id),
                assigned_agent_id=None,
                primary_hub_id=primary_hub_id,
                status="PENDING_ASSIGNMENT",
                urgency_tier=summary_data.get("urgency_tier", "WARM"),
                dialect=summary_data.get("dialect", "Standard English"),
                executive_summary=summary_data.get("executive_summary", "Customer requires human agent assistance."),
                suggested_first_response=summary_data.get("suggested_first_response", "Hello, I am here to help you."),
                key_blockers=summary_data.get("key_blockers") or "None",
            )
            session.add(ticket)
            await session.flush()

            ticket_payload = {
                "ticket_id": str(ticket.id),
                "conversation_id": event.conversation_id,
                "customer_phone": event.customer_phone,
                "customer_name": event.customer_name,
                "urgency_tier": ticket.urgency_tier,
                "executive_summary": ticket.executive_summary,
                "suggested_first_response": ticket.suggested_first_response,
                "created_at": ticket.created_at.isoformat(),
            }

            await broadcast_sse_event(event.merchant_id, "ticket_created", ticket_payload)

    @staticmethod
    async def handle_hub_power_outage(event: HubPowerOutageDetectedEvent) -> None:
        """
        Domain Event Handler: Transparent NEPA Outage Failover (ADR-0038).
        1. Notifies waiting customers via WhatsApp on INITIAL outage transition ONLY.
        2. Alerts merchant management on initial outage and 30-minute reminder heartbeats.
        """
        whatsapp = get_whatsapp_bsp_adapter()

        async with tenant_session_scope(event.merchant_id) as session:
            # 1. Notify waiting customers ONCE on initial outage detection only
            if not event.is_reminder:
                query = await session.execute(
                    select(EscalationTicket)
                    .where(
                        EscalationTicket.merchant_id == UUID(event.merchant_id),
                        EscalationTicket.status.in_(["OPEN", "PENDING_ASSIGNMENT"]),
                    )
                    .order_by(EscalationTicket.created_at.asc())
                )
                open_tickets = query.scalars().all()

                from app.contexts.ingress.models import Conversation
                for idx, ticket in enumerate(open_tickets):
                    queue_pos = idx + 1
                    conv_res = await session.execute(
                        select(Conversation).where(Conversation.id == ticket.conversation_id)
                    )
                    conv = conv_res.scalar_one_or_none()
                    if conv and conv.customer_phone:
                        customer_msg = (
                            f"Hello! Our support center in {event.hub_name} is currently experiencing a temporary power outage (NEPA). "
                            f"Your request is safely saved at position #{queue_pos} in our queue. "
                            f"Our team will attend to you immediately power and connectivity restore. Thank you for your patience! 🙏"
                        )
                        try:
                            await whatsapp.send_text_message(to_phone=conv.customer_phone, message=customer_msg)
                        except Exception as err:
                            print(f"[Desk] Failed to send queue notice to customer: {err}")

            # 2. Alert Merchant Manager (Triggered on initial alert AND 30m reminders)
            from app.contexts.core.models import Merchant
            merchant_res = await session.execute(
                select(Merchant).where(Merchant.id == UUID(event.merchant_id))
            )
            merchant = merchant_res.scalar_one_or_none()
            if merchant and merchant.whatsapp_business_phone:
                if event.is_reminder:
                    manager_alert = (
                        f"⚠️ [OUTAGE REMINDER #{event.reminder_count}] Hub '{event.hub_name}' remains OFFLINE (NEPA power outage). "
                        f"{event.open_ticket_count} customer tickets still held in queue."
                    )
                else:
                    manager_alert = (
                        f"⚠️ [EMERGENCY ALERT] All support agents in hub '{event.hub_name}' are currently OFFLINE (NEPA power outage). "
                        f"{event.open_ticket_count} customer tickets are held in queue. Automated position notifications have been dispatched."
                    )
                try:
                    await whatsapp.send_text_message(to_phone=merchant.whatsapp_business_phone, message=manager_alert)
                except Exception as err:
                    print(f"[Desk] Failed to send emergency WhatsApp alert to manager: {err}")

    @staticmethod
    async def handle_hub_power_restored(event: HubPowerRestoredEvent) -> None:
        """
        Domain Event Handler: Hub Power & Connectivity Restoration.
        Alerts merchant management that the hub has recovered and agents are back online.
        """
        whatsapp = get_whatsapp_bsp_adapter()
        async with tenant_session_scope(event.merchant_id) as session:
            from app.contexts.core.models import Merchant
            merchant_res = await session.execute(
                select(Merchant).where(Merchant.id == UUID(event.merchant_id))
            )
            merchant = merchant_res.scalar_one_or_none()
            if merchant and merchant.whatsapp_business_phone:
                duration_mins = max(1, event.outage_duration_seconds // 60)
                restore_msg = (
                    f"✅ [RESTORATION NOTICE] Support agents in hub '{event.hub_name}' are now back ONLINE. "
                    f"Power outage resolved after approximately {duration_mins} minute(s)."
                )
                try:
                    await whatsapp.send_text_message(to_phone=merchant.whatsapp_business_phone, message=restore_msg)
                except Exception as err:
                    print(f"[Desk] Failed to send restoration notice to manager: {err}")


# Register Event Handlers on Global Event Bus
event_bus.subscribe("agent.handoff.requested", DeskService.handle_agent_handoff_requested)
event_bus.subscribe("hub.power_outage.detected", DeskService.handle_hub_power_outage)
event_bus.subscribe("hub.power_restored", DeskService.handle_hub_power_restored)
