"""FastAPI Router for Compliance, PII Sanitization, and Chained Consent."""

from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_tenant_db, get_current_tenant, TenantContext
from app.contexts.compliance.schemas import (
    PiiSanitizeRequest,
    PiiSanitizeResponse,
    ConsentLogRequest,
    ConsentEventRead,
)
from app.contexts.compliance.services import ComplianceService

router = APIRouter(prefix="/compliance", tags=["Compliance & NDPA Consent"])


@router.post("/sanitize", response_model=PiiSanitizeResponse)
async def sanitize_pii_payload(payload: PiiSanitizeRequest):
    """
    Sanitizes and masks Nigerian BVN, NIN, NUBAN, and Card PAN identifiers before external routing.
    """
    return ComplianceService.sanitize_text(payload)


@router.post("/consent", response_model=ConsentEventRead, status_code=status.HTTP_201_CREATED)
async def record_consent_event(
    payload: ConsentLogRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Appends an NDPA 2023 consent action (OPT_IN, OPT_OUT_STOP, OPT_OUT_COMOT)
    to the immutable SHA-256 cryptographically chained consent ledger.
    """
    return await ComplianceService.log_chained_consent_event(
        session=db,
        merchant_id=UUID(tenant.merchant_id),
        request=payload,
    )
