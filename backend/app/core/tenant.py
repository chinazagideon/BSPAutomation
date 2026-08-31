"""Composite Multi-Channel Tenant Resolver and RLS Database Session Injection."""

from typing import Optional, AsyncGenerator
from pydantic import BaseModel, Field
from fastapi import Request, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.security import decode_access_token

# Fallback default seed merchant ID for local dev / testing
DEFAULT_DEV_MERCHANT_ID = "018f6c5a-8b1e-7230-a890-123456789abc"

security_bearer = HTTPBearer(auto_error=False)


class TenantContext(BaseModel):
    """Encapsulates the resolved multi-tenant merchant context for the current request."""
    merchant_id: str
    merchant_slug: Optional[str] = None
    source: str = Field(..., description="Ingress channel that resolved this tenant: JWT, HEADER, PATH, WEBHOOK, DEV_FALLBACK")
    user_id: Optional[str] = None
    role: Optional[str] = None


async def get_current_tenant(
    request: Request,
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    x_merchant_id: Optional[str] = Header(None, alias="X-Merchant-ID"),
) -> TenantContext:
    """
    Composite Multi-Channel Tenant Resolver:
    1. JWT Bearer Token (Dashboard, Agent Desk, Merchant Admin API)
    2. Explicit Header 'X-Merchant-ID'
    3. Path Parameter {merchant_id} in URL
    4. Development Fallback in dev/test mode
    """
    # 1. JWT Bearer Token
    if auth_credentials and auth_credentials.credentials:
        payload = decode_access_token(auth_credentials.credentials)
        if payload and "merchant_id" in payload:
            return TenantContext(
                merchant_id=payload["merchant_id"],
                merchant_slug=payload.get("merchant_slug"),
                source="JWT",
                user_id=payload.get("sub"),
                role=payload.get("role"),
            )

    # 2. X-Merchant-ID Header
    if x_merchant_id:
        return TenantContext(
            merchant_id=x_merchant_id,
            source="HEADER",
        )

    # 3. Path Parameters in URL
    path_params = request.path_params
    if "merchant_id" in path_params and path_params["merchant_id"]:
        return TenantContext(
            merchant_id=str(path_params["merchant_id"]),
            source="PATH",
        )

    # 4. Dev / Test Fallback
    if settings.ENVIRONMENT in ["development", "test"]:
        return TenantContext(
            merchant_id=DEFAULT_DEV_MERCHANT_ID,
            merchant_slug="demo-enterprise-sme",
            source="DEV_FALLBACK",
            role="SUPER_ADMIN",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not resolve active merchant tenant context",
    )


async def get_tenant_db(
    tenant: TenantContext = Depends(get_current_tenant),
) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency: Injects an AsyncSession with PostgreSQL Row-Level Security (RLS)
    scoped to the current merchant via 'SET LOCAL app.current_merchant_id = ...'.
    """
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                text("SET LOCAL app.current_merchant_id = :merchant_id"),
                {"merchant_id": str(tenant.merchant_id)},
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
