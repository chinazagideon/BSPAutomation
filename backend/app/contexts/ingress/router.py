"""FastAPI Router for Ingress Webhooks and 3-Stage Cascading NLU."""

from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response, status, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_tenant_db, get_current_tenant, TenantContext
from app.core.response import ApiResponse
from app.contexts.ingress.schemas import (
    NLUClassificationRequest,
    NLUClassificationResponse,
    WebhookPayload,
)
from app.contexts.ingress.services import IngressService
from app.core.config import settings

router = APIRouter(prefix="/ingress", tags=["Ingress & Cascading NLU"])


@router.get("/webhooks/{provider}")
async def verify_whatsapp_webhook_challenge(provider: str, request: Request):
    """Handles Provider Webhook verification challenge (e.g. Meta Cloud GET hub.challenge)."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.META_WEBHOOK_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhooks/{provider}", status_code=status.HTTP_200_OK)
async def receive_whatsapp_webhook(provider: str, request: Request):
    """
    Ingress Webhook Receiver: Delivers sub-25ms 200 OK acknowledgement to WhatsApp BSPs
    (whatsapp / meta / termii / twilio / 360dialog / sandbox).
    Validates provider HMAC signature, resolves tenant via phone number cache,
    persists raw webhook event, and offloads processing to ARQ Redis (ADR-0034, ADR-0047).
    """
    import json
    from app.adapters.whatsapp import get_whatsapp_bsp_adapter
    from app.contexts.core.services import MerchantIdentificationService
    from app.core.database import tenant_session_scope

    raw_body = await request.body()
    adapter = get_whatsapp_bsp_adapter(provider_slug=provider)
    headers_dict = dict(request.headers)

    # 1. Cryptographic HMAC Signature Verification (ADR-0034, ADR-0047)
    has_sig_header = bool(
        request.headers.get("X-Hub-Signature-256")
        or request.headers.get("x-hub-signature-256")
        or request.headers.get("X-Termii-Signature")
        or request.headers.get("x-termii-signature")
    )
    is_valid_sig = adapter.verify_webhook_signature(raw_body, headers_dict, settings.META_APP_SECRET)
    if has_sig_header and not is_valid_sig:
        raise HTTPException(status_code=403, detail="Invalid X-Hub-Signature-256 or webhook HMAC signature")
    elif not has_sig_header and settings.ENVIRONMENT in ["production", "staging"]:
        raise HTTPException(status_code=403, detail="Missing webhook signature header")

    # 2. Parse JSON body
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 3. Two-Tier Cached Multi-Channel Tenant Resolution (ADR-0031, ADR-0048)
    phone_number_id = IngressService.extract_phone_number_id(payload, provider_slug=provider)
    channel_ctx = await MerchantIdentificationService.resolve_inbound(phone_number_id) if phone_number_id else None
    merchant_id_str = channel_ctx.merchant_id if channel_ctx else None

    # Refresh 24h Customer Service Window in Local Sandbox when customer message arrives
    normalized = IngressService.normalize_inbound_payload(payload, provider_slug=provider)
    if normalized.has_message and normalized.sender_phone and phone_number_id:
        try:
            from app.sandbox.state import get_sandbox_store
            await get_sandbox_store().record_customer_inbound_turn(phone_number_id, normalized.sender_phone)
        except Exception:
            pass

    # Unknown phone ID fallback: acknowledge 200 OK to prevent retry storms (Q12)
    if not merchant_id_str:
        return {
            "status": "IGNORED_UNKNOWN_TENANT",
            "provider": adapter.provider_name,
            "phone_number_id": phone_number_id,
            "signature_verified": is_valid_sig,
        }

    # 4. Scoped RLS Audit Persistence & ARQ Redis Queueing
    resolved_provider_name = adapter.provider_name if provider.lower() != "whatsapp" else settings.WHATSAPP_BSP_PROVIDER
    async with tenant_session_scope(merchant_id_str) as session:
        return await IngressService.ingest_webhook_fast_ack(
            session=session,
            merchant_id=UUID(merchant_id_str),
            payload=payload,
            provider=resolved_provider_name,
            signature_verified=is_valid_sig,
        )



@router.post("/classify", response_model=ApiResponse[NLUClassificationResponse])
async def classify_message(
    payload: NLUClassificationRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    3-Stage Cascading Hybrid NLU Classifier:
    1. Trigram Fast-Path (0 tokens, ~2ms)
    2. Custom Local Model / HuggingFace (0 tokens, ~20ms)
    3. Google Gemini 3.7 Flash Escalation (~380ms)
    """
    result = await IngressService.classify_and_route(
        session=db,
        merchant_id=UUID(tenant.merchant_id),
        request=payload,
    )
    return ApiResponse.create(data=result)

