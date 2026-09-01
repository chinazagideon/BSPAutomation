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
async def receive_whatsapp_webhook(
    payload: Dict[str, Any],
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Ingress Webhook Receiver: Delivers sub-25ms 200 OK acknowledgement to Meta Cloud / Termii.
    Persists raw webhook event and offloads processing to the background worker pool (ADR-0033 Fast-ACK).
    """
    return await IngressService.ingest_webhook_fast_ack(
        session=db,
        merchant_id=UUID(tenant.merchant_id),
        payload=payload,
        provider=settings.WHATSAPP_BSP_PROVIDER,
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

