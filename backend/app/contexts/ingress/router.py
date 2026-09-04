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


@router.get("/webhooks/whatsapp")
async def verify_whatsapp_webhook_challenge(request: Request):
    """Handles Meta Cloud API Webhook verification challenge (GET hub.challenge)."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.META_WEBHOOK_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhooks/whatsapp", status_code=status.HTTP_200_OK)
async def receive_whatsapp_webhook(request: Request):
    """
    Ingress Webhook Receiver: Delivers sub-25ms 200 OK acknowledgement to Meta Cloud / Termii.
    Validates X-Hub-Signature-256 HMAC, resolves tenant via phone number cache,
    persists raw webhook event, and offloads processing to ARQ Redis (ADR-0034 Fast-ACK).
    """
    import json
    from app.core.security import verify_meta_webhook_signature
    from app.core.tenant import resolve_merchant_from_phone
    from app.core.database import tenant_session_scope

    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("x-hub-signature-256")

    # 1. Cryptographic HMAC Signature Verification (ADR-0034)
    is_valid_sig = True
    if signature:
        is_valid_sig = verify_meta_webhook_signature(raw_body, signature, settings.META_APP_SECRET)
        if not is_valid_sig:
            raise HTTPException(status_code=403, detail="Invalid X-Hub-Signature-256 HMAC signature")
    elif settings.ENVIRONMENT in ["production", "staging"]:
        raise HTTPException(status_code=403, detail="Missing X-Hub-Signature-256 header")

    # 2. Parse JSON body
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 3. Two-Tier Cached Webhook Tenant Resolution (ADR-0031)
    phone_number_id = IngressService.extract_phone_number_id(payload)
    merchant_id_str = await resolve_merchant_from_phone(phone_number_id) if phone_number_id else None

    # Unknown phone ID fallback: acknowledge 200 OK to prevent Meta retry storms (Q12)
    if not merchant_id_str:
        return {
            "status": "IGNORED_UNKNOWN_TENANT",
            "phone_number_id": phone_number_id,
            "signature_verified": is_valid_sig,
        }

    # 4. Scoped RLS Audit Persistence & ARQ Redis Queueing
    async with tenant_session_scope(merchant_id_str) as session:
        return await IngressService.ingest_webhook_fast_ack(
            session=session,
            merchant_id=UUID(merchant_id_str),
            payload=payload,
            provider=settings.WHATSAPP_BSP_PROVIDER,
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

