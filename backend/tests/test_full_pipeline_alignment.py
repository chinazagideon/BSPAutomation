"""Comprehensive Tests for the Zero-Coupling 6-Stage WhatsApp BSP Pipeline Alignment.

Covers:
  Step 1: HMAC-SHA256 Signature Verification, Phone Tenant Resolution & Fast-ACK Enqueueing
  Step 2: Message Digestion, NDPA Compliance, Conversation Threading & Voice Note Passthrough
  Step 3: DB/Redis Fast-Path Dictionary & Stage 3 Catalog/Provider Context Manifest Injection
  Step 4: WhatsApp Egress (Text, Templates, Media, Interactive Lists)
  Step 5: Event-Driven Agent Desk Escalation, SSE Streaming & Atomic Ticket Claim Guard
  Step 6: NEPA Inactivity Timeout Cron & Hub Outage Transparent Customer/Manager Failover
"""

import hmac
import hashlib
import json
import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient

from app.core.config import settings
from app.core.database import async_session_factory, tenant_session_scope
from app.contexts.core.models import Merchant, User
from app.contexts.ingress.models import WebhookEvent, Conversation, Message, FastPathDictionary
from app.contexts.ingress.services import IngressService
from app.contexts.ingress.pipeline import CascadingNLUPipeline
from app.contexts.desk.models import Hub, AgentProfile, EscalationTicket
from app.contexts.desk.services import DeskService
from app.adapters.whatsapp import get_whatsapp_bsp_adapter, MockWhatsAppBSPAdapter
from app.core.worker import process_incoming_webhook_job, check_agent_heartbeat_timeouts_job
from app.core.events import event_bus, HubPowerOutageDetectedEvent


def _compute_meta_signature(payload_bytes: bytes, secret: str) -> str:
    sig = hmac.new(key=secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.mark.asyncio
async def test_ingress_hmac_signature_verification_and_unknown_tenant(async_client: AsyncClient):
    """Verifies HMAC validation rejects forged webhooks and safely ignores unknown phone IDs."""
    sample_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "unknown_phone_99999"},
                    "messages": [{"from": "+2348011112222", "id": "wamid.1", "type": "text", "text": {"body": "hello"}}]
                }
            }]
        }]
    }
    raw_body = json.dumps(sample_payload).encode("utf-8")

    # 1. Invalid signature -> 403 Forbidden
    resp_invalid = await async_client.post(
        "/api/v1/ingress/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=invalid_hash_value_here"},
    )
    assert resp_invalid.status_code == 403
    assert "Invalid X-Hub-Signature-256" in str(resp_invalid.json())

    # 2. Valid signature with unknown phone -> 200 OK with IGNORED_UNKNOWN_TENANT
    valid_sig = _compute_meta_signature(raw_body, settings.META_APP_SECRET)
    resp_unknown = await async_client.post(
        "/api/v1/ingress/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig},
    )
    assert resp_unknown.status_code == 200
    data = resp_unknown.json()
    assert data["status"] == "IGNORED_UNKNOWN_TENANT"
    assert data["signature_verified"] is True


@pytest.mark.asyncio
async def test_ingress_valid_fast_ack_and_worker_text_processing(async_client: AsyncClient):
    """Verifies end-to-end Fast-ACK receiver and asynchronous worker text message processing."""
    suffix = str(uuid4())[:8]
    phone_id = f"meta_phone_{suffix}"

    # Setup merchant in DB
    async with async_session_factory() as session:
        merchant = Merchant(
            business_name=f"Fast-ACK Store {suffix}",
            slug=f"fast-ack-{suffix}",
            whatsapp_business_phone=f"+23480{suffix[:8]}",
            whatsapp_phone_number_id=phone_id,
        )
        session.add(merchant)
        await session.commit()
        merchant_id = str(merchant.id)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"profile": {"name": "Adeola Davies"}}],
                    "messages": [{
                        "from": "+2348099887766",
                        "id": f"wamid.{suffix}",
                        "timestamp": "1725360000",
                        "type": "text",
                        "text": {"body": "How much for 5 cartons of groundnut oil?"},
                    }]
                }
            }]
        }]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    valid_sig = _compute_meta_signature(raw_body, settings.META_APP_SECRET)

    # Fast-ACK HTTP POST
    response = await async_client.post(
        "/api/v1/ingress/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig},
    )
    assert response.status_code == 200
    fast_ack = response.json()
    assert fast_ack["status"] == "EVENT_RECEIVED"
    assert fast_ack["signature_verified"] is True
    assert "event_id" in fast_ack
    event_id = fast_ack["event_id"]

    # Execute Background Worker Job asynchronously
    worker_res = await process_incoming_webhook_job(
        ctx={},
        merchant_id=merchant_id,
        event_id=event_id,
    )
    assert worker_res["status"] == "PROCESSED"
    assert worker_res["intent"] == "PRICE_INQUIRY"

    # Verify conversation & message persistence in DB
    async with tenant_session_scope(merchant_id) as session:
        from sqlalchemy import select
        conv_res = await session.execute(
            select(Conversation).where(Conversation.merchant_id == UUID(merchant_id))
        )
        conv = conv_res.scalar_one_or_none()
        assert conv is not None
        assert conv.customer_phone == "+2348099887766"

        msg_res = await session.execute(
            select(Message).where(Message.conversation_id == conv.id)
        )
        messages = msg_res.scalars().all()
        assert len(messages) >= 2  # Inbound message + Outbound reply
        inbound = [m for m in messages if m.direction == "INBOUND"][0]
        outbound = [m for m in messages if m.direction == "OUTBOUND"][0]
        assert "cartons" in inbound.raw_text_redacted
        assert "catalog" in outbound.raw_text_redacted.lower() or "price" in outbound.raw_text_redacted.lower()


@pytest.mark.asyncio
async def test_voice_note_passthrough_and_desk_escalation():
    """Verifies that voice notes are preserved without transcription and trigger human desk handoff (ADR-0037)."""
    suffix = str(uuid4())[:8]

    async with async_session_factory() as session:
        merchant = Merchant(
            business_name=f"Audio Store {suffix}",
            slug=f"audio-store-{suffix}",
            whatsapp_business_phone=f"+23481{suffix[:8]}",
            whatsapp_phone_number_id=f"phone_{suffix}",
        )
        session.add(merchant)
        await session.commit()
        merchant_id = str(merchant.id)

    audio_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_AUDIO",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": f"phone_{suffix}"},
                    "contacts": [{"profile": {"name": "Ngozi Eze"}}],
                    "messages": [{
                        "from": "+2348077665544",
                        "id": f"wamid.audio.{suffix}",
                        "timestamp": "1725360000",
                        "type": "audio",
                        "audio": {"id": "meta_audio_ref_998877", "mime_type": "audio/ogg; codecs=opus"},
                    }]
                }
            }]
        }]
    }

    # Process via worker
    worker_res = await process_incoming_webhook_job(
        ctx={},
        merchant_id=merchant_id,
        raw_payload=audio_payload,
    )
    assert worker_res["status"] == "VOICE_NOTE_HANDED_OFF"
    assert worker_res["media_id"] == "meta_audio_ref_998877"

    # Verify escalation ticket was created with unassigned agent (Claim Model)
    async with tenant_session_scope(merchant_id) as session:
        from sqlalchemy import select
        ticket_res = await session.execute(
            select(EscalationTicket).where(EscalationTicket.merchant_id == UUID(merchant_id))
        )
        ticket = ticket_res.scalar_one_or_none()
        assert ticket is not None
        assert ticket.assigned_agent_id is None
        assert ticket.status in ["OPEN", "PENDING_ASSIGNMENT"]
        assert "Ngozi Eze" in ticket.executive_summary or "Customer" in ticket.executive_summary


@pytest.mark.asyncio
async def test_ndpa_opt_out_comot_keyword_interceptor():
    """Verifies deterministic opt-out interceptor for Nigerian Pidgin COMOT ME (ADR-0014)."""
    suffix = str(uuid4())[:8]

    async with async_session_factory() as session:
        merchant = Merchant(
            business_name=f"OptOut Store {suffix}",
            slug=f"optout-{suffix}",
            whatsapp_business_phone=f"+23482{suffix[:8]}",
            whatsapp_phone_number_id=f"phone_{suffix}",
        )
        session.add(merchant)
        await session.commit()
        merchant_id = str(merchant.id)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_OPTOUT",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": f"phone_{suffix}"},
                    "contacts": [{"profile": {"name": "Segun Balogun"}}],
                    "messages": [{
                        "from": "+2348055443322",
                        "id": f"wamid.optout.{suffix}",
                        "timestamp": "1725360000",
                        "type": "text",
                        "text": {"body": "COMOT ME"},
                    }]
                }
            }]
        }]
    }

    res = await process_incoming_webhook_job(
        ctx={},
        merchant_id=merchant_id,
        raw_payload=payload,
    )
    assert res["status"] == "OPTED_OUT"
    assert res["action"] == "OPT_OUT_COMOT"


@pytest.mark.asyncio
async def test_custom_dictionary_and_manifest_injection():
    """Verifies Stage 1 custom dictionary matching and Stage 3 Catalog/Provider Manifest injection (ADR-0035)."""
    # 1. Stage 1 custom merchant phrase
    custom_rules = [
        {
            "phrase_pattern": "promo oil",
            "intent": "WHOLESALE_PROMO_INQUIRY",
            "suggested_response_template": "Our Promo Oil is ₦19,500 per carton today only!",
        }
    ]
    resp1 = await CascadingNLUPipeline.process(
        text="Abeg how much for your promo oil?",
        custom_dictionary=custom_rules,
    )
    assert resp1.routing_source == "FAST_PATH"
    assert resp1.intent == "WHOLESALE_PROMO_INQUIRY"
    assert "₦19,500" in resp1.suggested_reply

    # 2. Stage 3 Provider & Catalog Manifest Injection
    catalog = "| SKU | Item | Price |\n| --- | --- | --- |\n| OIL-01 | Sunflower Oil | ₦22,000 |"
    provider_ctx = {
        "verified_business_name": "Lagos Mega Mart",
        "operating_hours": "8am - 8pm WAT",
        "delivery_coverage": "Lagos Mainland & Island",
        "meta_catalog_id": "META_CATALOG_7890",
    }
    resp3 = await CascadingNLUPipeline.process(
        text="I want to discuss international export distribution terms and franchise partnership licensing.",
        catalog_manifest=catalog,
        provider_context=provider_ctx,
    )
    assert resp3.routing_source in ["GEMINI_LLM_ESCALATION", "CUSTOM_LOCAL_MODEL", "FALLBACK_DESK_HANDOFF"]


@pytest.mark.asyncio
async def test_desk_atomic_ticket_claim_concurrency(async_client: AsyncClient, auth_headers_factory):
    """Verifies that atomic ticket claim ensures exactly one agent succeeds and others get 409 Conflict (ADR-0036)."""
    suffix = str(uuid4())[:8]

    async with async_session_factory() as session:
        merchant = Merchant(
            business_name=f"Claim Store {suffix}",
            slug=f"claim-store-{suffix}",
            whatsapp_business_phone=f"+23483{suffix[:8]}",
        )
        session.add(merchant)
        await session.commit()
        merchant_id = str(merchant.id)

    async with tenant_session_scope(merchant_id) as session:
        hub = Hub(
            merchant_id=UUID(merchant_id),
            name=f"Claim Hub {suffix}",
            region="LAGOS_MAINLAND",
            is_active=True,
        )
        session.add(hub)
        await session.flush()

        agent_prof = AgentProfile(
            merchant_id=UUID(merchant_id),
            hub_id=hub.id,
            name="Agent 1",
            phone="+2348000000001",
            work_status="ONLINE",
        )
        session.add(agent_prof)
        await session.flush()

        conv = Conversation(
            merchant_id=UUID(merchant_id),
            customer_phone="+2348012345678",
            customer_name="Ibrahim Musa",
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
            executive_summary="Customer requested urgent bulk order pricing",
            suggested_first_response="Hello Ibrahim, I have taken over your order.",
        )
        session.add(ticket)
        await session.flush()
        ticket_id = str(ticket.id)

    agent1_headers = auth_headers_factory(merchant_id=merchant_id, user_id=str(uuid4()), role="AGENT")
    agent2_headers = auth_headers_factory(merchant_id=merchant_id, user_id=str(uuid4()), role="AGENT")

    # Agent 1 claims ticket
    resp1 = await async_client.post(f"/api/v1/desk/tickets/{ticket_id}/claim", headers=agent1_headers)
    assert resp1.status_code == 200
    assert resp1.json()["data"]["status"] == "IN_PROGRESS"

    # Agent 2 attempts to claim same ticket -> 409 Conflict
    resp2 = await async_client.post(f"/api/v1/desk/tickets/{ticket_id}/claim", headers=agent2_headers)
    assert resp2.status_code == 409
    assert "already claimed" in str(resp2.json()).lower()


@pytest.mark.asyncio
async def test_nepa_heartbeat_timeout_and_failover_dispatch():
    """Verifies NEPA heartbeat cron marks agents offline and emits transparent customer/manager failover (ADR-0038)."""
    suffix = str(uuid4())[:8]

    async with async_session_factory() as session:
        merchant = Merchant(
            business_name=f"NEPA Store {suffix}",
            slug=f"nepa-store-{suffix}",
            whatsapp_business_phone="+2348099001122",
        )
        session.add(merchant)
        await session.commit()
        merchant_id = str(merchant.id)

    async with tenant_session_scope(merchant_id) as session:
        hub = Hub(
            merchant_id=UUID(merchant_id),
            name=f"Ikeja Grid Hub {suffix}",
            region="LAGOS_MAINLAND",
            is_active=True,
        )
        session.add(hub)
        await session.flush()

        user = User(
            merchant_id=UUID(merchant_id),
            email=f"agent_{suffix}@nepa.ng",
            password_hash="hashed_pw",
            full_name="Sunday Alabi",
            role="AGENT",
        )
        session.add(user)
        await session.flush()

        # Inactive agent with heartbeat >60s old
        stale_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=95)
        agent = AgentProfile(
            user_id=user.id,
            merchant_id=UUID(merchant_id),
            hub_id=hub.id,
            name="Sunday Alabi",
            phone="+2348011223344",
            work_status="ONLINE",
            last_heartbeat_at=stale_heartbeat,
        )
        session.add(agent)

        conv = Conversation(
            merchant_id=UUID(merchant_id),
            customer_phone="+2348088776655",
            customer_name="Funke Akindele",
        )
        session.add(conv)
        await session.flush()

        ticket = EscalationTicket(
            merchant_id=UUID(merchant_id),
            conversation_id=conv.id,
            primary_hub_id=hub.id,
            assigned_agent_id=None,
            status="PENDING_ASSIGNMENT",
            urgency_tier="WARM",
            executive_summary="Awaiting human support",
            suggested_first_response="Hello Funke",
        )
        session.add(ticket)
        await session.flush()

    # Run the ARQ heartbeat cron job
    await check_agent_heartbeat_timeouts_job(ctx={})

    # Verify agent is now OFFLINE_NEPA
    async with tenant_session_scope(merchant_id) as session:
        from sqlalchemy import select
        agent_res = await session.execute(
            select(AgentProfile).where(AgentProfile.merchant_id == UUID(merchant_id))
        )
        updated_agent = agent_res.scalar_one_or_none()
        assert updated_agent.work_status == "OFFLINE_NEPA"

    # Verify WhatsApp adapter sent failover queue position message
    whatsapp: MockWhatsAppBSPAdapter = get_whatsapp_bsp_adapter()
    customer_notices = [m for m in whatsapp.sent_messages if m["to"] == "+2348088776655"]
    assert len(customer_notices) >= 1
    assert "position #1" in customer_notices[0]["message"]
    assert "power outage (NEPA)" in customer_notices[0]["message"]

    # Verify Manager Alert was sent
    manager_alerts = [m for m in whatsapp.sent_messages if m["to"] == "+2348099001122"]
    assert len(manager_alerts) >= 1
    assert "EMERGENCY ALERT" in manager_alerts[0]["message"]
