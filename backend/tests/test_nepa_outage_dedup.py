"""Unit and Integration Tests for NEPA Outage Deduplication & Decoupled Dispatch (ADR-0038)."""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta

from app.core.database import async_session_factory, tenant_session_scope
from app.contexts.core.models import Merchant, User
from app.contexts.desk.models import Hub, AgentProfile, EscalationTicket
from app.contexts.ingress.models import Conversation
from app.core.worker import (
    check_agent_heartbeat_timeouts_job,
    _get_outage_state,
    _set_outage_state,
    _delete_outage_state,
    _IN_MEMORY_OUTAGE_CACHE,
)
from app.adapters.whatsapp import get_whatsapp_bsp_adapter


@pytest.mark.asyncio
async def test_nepa_outage_deduplication_and_reminder_lifecycle():
    """
    Validates the end-to-end outage lifecycle:
    1. Initial detection -> Customer notice #1 + Emergency manager alert sent.
    2. 30s subsequent poll -> Deduplicated, NO new notices sent.
    3. 30m simulated elapsed -> Manager reminder #1 sent, customer NOT spammed.
    4. Recovery -> State cleared, Restoration notice sent to manager.
    """
    _IN_MEMORY_OUTAGE_CACHE.clear()
    whatsapp = get_whatsapp_bsp_adapter()
    whatsapp.sent_messages.clear()

    suffix = str(uuid4())[:8]
    customer_phone = f"+23480{suffix[:8]}"
    manager_phone = f"+23481{suffix[:8]}"

    # Setup merchant, hub, stale agent, and open escalation ticket
    async with async_session_factory() as session:
        merchant = Merchant(
            business_name=f"Dedupe Store {suffix}",
            slug=f"dedupe-store-{suffix}",
            whatsapp_business_phone=manager_phone,
        )
        session.add(merchant)
        await session.commit()
        merchant_id = str(merchant.id)

    async with tenant_session_scope(merchant_id) as session:
        hub = Hub(
            merchant_id=UUID(merchant_id),
            name=f"Surulere Hub {suffix}",
            region="LAGOS_MAINLAND",
            is_active=True,
        )
        session.add(hub)
        await session.flush()
        hub_id = str(hub.id)

        user = User(
            merchant_id=UUID(merchant_id),
            email=f"agent_{suffix}@dedupe.ng",
            password_hash="hashed_pw",
            full_name="Bisi Akande",
            role="AGENT",
        )
        session.add(user)
        await session.flush()

        stale_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)
        agent = AgentProfile(
            user_id=user.id,
            merchant_id=UUID(merchant_id),
            hub_id=hub.id,
            name="Bisi Akande",
            phone="+2348011223344",
            work_status="ONLINE",
            last_heartbeat_at=stale_heartbeat,
        )
        session.add(agent)

        conv = Conversation(
            merchant_id=UUID(merchant_id),
            customer_phone=customer_phone,
            customer_name="Emeka Obi",
        )
        session.add(conv)
        await session.flush()

        ticket = EscalationTicket(
            merchant_id=UUID(merchant_id),
            conversation_id=conv.id,
            primary_hub_id=hub.id,
            assigned_agent_id=None,
            status="PENDING_ASSIGNMENT",
            urgency_tier="HOT",
            executive_summary="VIP customer waiting",
            suggested_first_response="Hello Emeka",
        )
        session.add(ticket)
        await session.flush()

    # -------------------------------------------------------------------------
    # STAGE 1: Initial Outage Detection
    # -------------------------------------------------------------------------
    await check_agent_heartbeat_timeouts_job(ctx={})

    # Assert Redis / In-memory state created
    state = await _get_outage_state(redis=None, hub_id=hub_id)
    assert state is not None
    assert state["reminder_count"] == 0
    assert "outage_started_at" in state

    # Assert 1 customer notice and 1 manager alert sent
    customer_msgs = [m for m in whatsapp.sent_messages if m["to"] == customer_phone]
    manager_msgs = [m for m in whatsapp.sent_messages if m["to"] == manager_phone]
    assert len(customer_msgs) == 1
    assert "power outage (NEPA)" in customer_msgs[0]["message"]
    assert len(manager_msgs) == 1
    assert "EMERGENCY ALERT" in manager_msgs[0]["message"]

    # -------------------------------------------------------------------------
    # STAGE 2: Subsequent 30s Poll (Deduplication)
    # -------------------------------------------------------------------------
    # Run cron again immediately (simulating 30s poll without time advance)
    await check_agent_heartbeat_timeouts_job(ctx={})

    # Verify no duplicate messages sent!
    customer_msgs = [m for m in whatsapp.sent_messages if m["to"] == customer_phone]
    manager_msgs = [m for m in whatsapp.sent_messages if m["to"] == manager_phone]
    assert len(customer_msgs) == 1, "Customer should NOT receive duplicate outage messages on next poll!"
    assert len(manager_msgs) == 1, "Manager should NOT receive duplicate alerts on 30s poll!"

    # -------------------------------------------------------------------------
    # STAGE 3: 30-Minute Reminder Policy
    # -------------------------------------------------------------------------
    # Simulate that 31 minutes have elapsed since last alert
    simulated_last_alert = datetime.now(timezone.utc) - timedelta(minutes=31)
    state["last_alerted_at"] = simulated_last_alert.isoformat()
    await _set_outage_state(redis=None, hub_id=hub_id, state=state)

    # Run cron
    await check_agent_heartbeat_timeouts_job(ctx={})

    # Verify: Customer received ZERO new messages, Manager received REMINDER #1
    customer_msgs = [m for m in whatsapp.sent_messages if m["to"] == customer_phone]
    manager_msgs = [m for m in whatsapp.sent_messages if m["to"] == manager_phone]
    assert len(customer_msgs) == 1, "Customers must never receive periodic reminder alerts!"
    assert len(manager_msgs) == 2, "Manager should receive periodic reminder!"
    assert "OUTAGE REMINDER #1" in manager_msgs[1]["message"]

    # State updated with incremented reminder count
    updated_state = await _get_outage_state(redis=None, hub_id=hub_id)
    assert updated_state["reminder_count"] == 1

    # -------------------------------------------------------------------------
    # STAGE 4: Recovery Transition (Agents Return Online)
    # -------------------------------------------------------------------------
    async with tenant_session_scope(merchant_id) as session:
        from sqlalchemy import update
        await session.execute(
            update(AgentProfile)
            .where(AgentProfile.merchant_id == UUID(merchant_id))
            .values(work_status="ONLINE", last_heartbeat_at=datetime.now(timezone.utc))
        )

    # Run cron
    await check_agent_heartbeat_timeouts_job(ctx={})

    # Verify: State is deleted
    recovered_state = await _get_outage_state(redis=None, hub_id=hub_id)
    assert recovered_state is None, "Outage state must be cleared when agents return online!"

    # Verify: Restoration Notice sent to Manager
    manager_msgs = [m for m in whatsapp.sent_messages if m["to"] == manager_phone]
    assert len(manager_msgs) == 3, "Manager should receive restoration notice!"
    assert "RESTORATION NOTICE" in manager_msgs[2]["message"]
    assert "back ONLINE" in manager_msgs[2]["message"]
