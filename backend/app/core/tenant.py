"""Strict Multi-Channel Tenant Resolver, RBAC Hierarchy Guards, and Two-Tier Webhook Cache."""

import time
from typing import Optional, AsyncGenerator, Dict
from pydantic import BaseModel, Field
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.security import decode_access_token

security_bearer = HTTPBearer(auto_error=False)


# -----------------------------------------------------------------------------
# 1. LINEAR INTEGER ROLE HIERARCHY (ADR-0029)
# -----------------------------------------------------------------------------
ROLE_RANKS: Dict[str, int] = {
    "OWNER": 100,
    "ADMIN": 80,
    "MANAGER": 60,
    "AGENT": 40,
    "READ_ONLY": 20,
}


class TenantContext(BaseModel):
    """Encapsulates the resolved multi-tenant merchant context for the current request."""
    merchant_id: str
    merchant_slug: Optional[str] = None
    source: str = Field(..., description="Channel that resolved this tenant: JWT, WEBHOOK, API_KEY")
    user_id: Optional[str] = None
    role: Optional[str] = None


# -----------------------------------------------------------------------------
# 2. STRICT CRYPTOGRAPHIC TENANT RESOLVER (ADR-0026)
# -----------------------------------------------------------------------------
async def get_current_tenant(
    request: Request,
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> TenantContext:
    """
    Strict Cryptographic Multi-Tenant Resolver:
    1. Extracts JWT from Authorization: Bearer <token> header or HttpOnly 'access_token' cookie.
    2. Cryptographically validates signature, issuer, and expiration.
    3. Rejects any unverified header or path overrides.
    """
    token = None
    if auth_credentials and auth_credentials.credentials:
        token = auth_credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload or "merchant_id" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or tampered access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TenantContext(
        merchant_id=str(payload["merchant_id"]),
        merchant_slug=payload.get("merchant_slug"),
        source="JWT",
        user_id=payload.get("sub"),
        role=payload.get("role"),
    )


# -----------------------------------------------------------------------------
# 3. RBAC MINIMUM ROLE GUARDS (ADR-0029)
# -----------------------------------------------------------------------------
def require_min_role(min_role: str):
    """
    Declarative FastAPI Dependency: Enforces that the caller has a role rank >= required role.
    Example: require_min_role("MANAGER") grants access to MANAGER, ADMIN, and OWNER.
    """
    required_rank = ROLE_RANKS.get(min_role.upper(), 0)

    async def role_checker(tenant: TenantContext = Depends(get_current_tenant)) -> TenantContext:
        user_role = (tenant.role or "").upper()
        user_rank = ROLE_RANKS.get(user_role, 0)
        if user_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires at least '{min_role}' role (Current role: '{tenant.role}')",
            )
        return tenant

    return role_checker


# High-Risk Action Overrides
require_owner = require_min_role("OWNER")
require_owner_or_admin = require_min_role("ADMIN")
require_agent = require_min_role("AGENT")


# -----------------------------------------------------------------------------
# 4. ROW-LEVEL SECURITY (RLS) DATABASE INJECTION
# -----------------------------------------------------------------------------
async def get_tenant_db(
    tenant: TenantContext = Depends(get_current_tenant),
) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency: Injects an AsyncSession with PostgreSQL Row-Level Security (RLS)
    strictly scoped to the verified tenant via 'SET LOCAL app.current_merchant_id = ...'.
    """
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_merchant_id', :merchant_id, true)"),
                {"merchant_id": str(tenant.merchant_id)},
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


# -----------------------------------------------------------------------------
# 5. TWO-TIER CACHED WEBHOOK TENANT RESOLVER (ADR-0031)
# -----------------------------------------------------------------------------
# Process-local In-Memory TTL Cache: phone_number_id -> (merchant_id, expire_at)
_PHONE_TENANT_CACHE: Dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 300.0  # 5 minutes


async def resolve_merchant_from_phone(
    phone_number_id: str,
    db: Optional[AsyncSession] = None,
) -> Optional[str]:
    """
    Resolves merchant_id from external WhatsApp phone_number_id using Two-Tier Caching:
    1. Tier 1: Local In-Memory TTL Cache (<0.05ms)
    2. Tier 2: PostgreSQL DB Fallback & Cache Hydration
    """
    now = time.time()
    # 1. Tier 1: Check in-memory cache
    if phone_number_id in _PHONE_TENANT_CACHE:
        merchant_id, exp = _PHONE_TENANT_CACHE[phone_number_id]
        if now < exp:
            return merchant_id
        del _PHONE_TENANT_CACHE[phone_number_id]

    # 2. Database Fallback
    from app.contexts.core.models import Merchant

    if db is not None:
        result = await db.execute(
            select(Merchant.id).where(
                (Merchant.whatsapp_phone_number_id == phone_number_id) |
                (Merchant.whatsapp_business_phone == phone_number_id)
            )
        )
        merchant_id_uuid = result.scalar_one_or_none()
        if merchant_id_uuid:
            m_id = str(merchant_id_uuid)
            _PHONE_TENANT_CACHE[phone_number_id] = (m_id, now + _CACHE_TTL_SECONDS)
            return m_id
    else:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Merchant.id).where(
                    (Merchant.whatsapp_phone_number_id == phone_number_id) |
                    (Merchant.whatsapp_business_phone == phone_number_id)
                )
            )
            merchant_id_uuid = result.scalar_one_or_none()
            if merchant_id_uuid:
                m_id = str(merchant_id_uuid)
                _PHONE_TENANT_CACHE[phone_number_id] = (m_id, now + _CACHE_TTL_SECONDS)
                return m_id

    return None


def invalidate_phone_tenant_cache(phone_number_id: str) -> None:
    """Evicts a phone number from the in-memory tenant cache upon configuration update."""
    _PHONE_TENANT_CACHE.pop(phone_number_id, None)
