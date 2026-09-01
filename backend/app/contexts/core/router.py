"""FastAPI Router for Tenant Core Infrastructure, Authentication, and RBAC Management."""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.tenant import (
    get_current_tenant,
    require_min_role,
    require_owner_or_admin,
    TenantContext,
    ROLE_RANKS,
)
from app.core.security import set_auth_cookies, clear_auth_cookies
from app.contexts.core.schemas import (
    MerchantCreate,
    MerchantRead,
    MerchantRegisterRequest,
    UserLogin,
    UserCreate,
    UserRead,
    TokenRefreshRequest,
    TokenResponse,
    UserProfileResponse,
)
from app.contexts.core.services import CoreService, AuthService

router = APIRouter(prefix="/core", tags=["Core Tenant & Authentication"])


# -----------------------------------------------------------------------------
# 1. AUTHENTICATION & ONBOARDING ENDPOINTS
# -----------------------------------------------------------------------------
@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new merchant & initial OWNER user",
)
async def register_merchant(
    payload: MerchantRegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Atomic SME Onboarding:
    - Registers merchant tenant and initial 'OWNER' user account.
    - Automatically provisions standard Chart of Accounts.
    - Returns JWT access token + rotating refresh token in payload and HttpOnly cookies.
    """
    token_response, raw_refresh_token, owner, merchant = await AuthService.register_merchant_and_owner(
        db, payload
    )
    set_auth_cookies(response, token_response.access_token, raw_refresh_token)
    return token_response


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue token pair",
)
async def login_user(
    payload: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Authenticates operator / desk agent:
    - Validates email and password against bcrypt hash.
    - Enforces 5-attempt Account Lockout Governor (ADR-0032).
    - Returns short-lived JWT (15 min) + single-use rotating refresh token.
    """
    token_response, raw_refresh_token, user, merchant = await AuthService.authenticate_user(
        db, payload
    )
    set_auth_cookies(response, token_response.access_token, raw_refresh_token)
    return token_response


@router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate single-use refresh token",
)
async def refresh_access_token(
    request: Request,
    response: Response,
    payload: Optional[TokenRefreshRequest] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Rotates single-use refresh token:
    - Allows 5-second concurrency grace leeway for multi-tab sessions.
    - Enforces automatic token family revocation upon detected replay theft.
    - Returns fresh short-lived JWT and new child refresh token.
    """
    raw_token = None
    if payload and payload.refresh_token:
        raw_token = payload.refresh_token
    elif "refresh_token" in request.cookies:
        raw_token = request.cookies.get("refresh_token")

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token in payload or cookie",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_response, new_raw_token = await AuthService.rotate_refresh_token(db, raw_token)
    set_auth_cookies(response, token_response.access_token, new_raw_token)
    return token_response


@router.post(
    "/auth/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke active token family and clear session",
)
async def logout_user(
    request: Request,
    response: Response,
    payload: Optional[TokenRefreshRequest] = None,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db_session),
):
    """Revokes active token families and clears HttpOnly browser cookies."""
    raw_token = None
    if payload and payload.refresh_token:
        raw_token = payload.refresh_token
    elif "refresh_token" in request.cookies:
        raw_token = request.cookies.get("refresh_token")

    user_id = UUID(tenant.user_id) if tenant.user_id else None
    if user_id:
        await AuthService.logout_user(db, user_id=user_id, raw_refresh_token=raw_token)

    clear_auth_cookies(response)
    return {"status": "logged_out", "detail": "Session terminated successfully"}


@router.get(
    "/auth/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user and tenant profile",
)
async def get_current_user_profile(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns profile information, role hierarchy rank, and merchant settings for the caller."""
    if not tenant.user_id:
        raise HTTPException(status_code=401, detail="User context missing from token")

    user = await AuthService.get_user_by_id(db, UUID(tenant.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    merchant = await CoreService.get_merchant_by_id(db, UUID(tenant.merchant_id))
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant tenant not found")

    user_read = UserRead.model_validate(user)
    merchant_read = MerchantRead.model_validate(merchant)
    role_rank = ROLE_RANKS.get((user.role or "").upper(), 0)

    return UserProfileResponse(
        user=user_read,
        merchant=merchant_read,
        role_rank=role_rank,
        active_channel=tenant.source,
    )


# -----------------------------------------------------------------------------
# 2. RBAC TEAM MANAGEMENT (OWNER & ADMIN ONLY)
# -----------------------------------------------------------------------------
@router.post(
    "/auth/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new team member under active merchant",
)
async def create_team_user(
    payload: UserCreate,
    tenant: TenantContext = Depends(require_owner_or_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Provisions a new staff member (MANAGER, AGENT, READ_ONLY) under the active merchant.
    Requires caller to possess at least 'ADMIN' role rank.
    """
    return await AuthService.create_merchant_user(
        db, merchant_id=UUID(tenant.merchant_id), data=payload
    )


@router.get(
    "/auth/users",
    response_model=List[UserRead],
    status_code=status.HTTP_200_OK,
    summary="List all team members for active merchant",
)
async def list_team_users(
    tenant: TenantContext = Depends(require_owner_or_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Lists all team members under the caller's merchant tenant."""
    users = await AuthService.list_merchant_users(db, merchant_id=UUID(tenant.merchant_id))
    return [UserRead.model_validate(u) for u in users]


# -----------------------------------------------------------------------------
# 3. MERCHANT PROFILE MANAGEMENT
# -----------------------------------------------------------------------------
@router.post("/merchants", response_model=MerchantRead, status_code=status.HTTP_201_CREATED)
async def create_merchant(
    payload: MerchantCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Registers a new Nigerian SME tenant on the platform."""
    return await CoreService.create_merchant(db, payload)


@router.get("/merchants", response_model=List[MerchantRead])
async def list_merchants(
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
):
    """Lists registered merchant profiles."""
    return await CoreService.list_merchants(db, limit)


@router.get("/merchants/me", response_model=MerchantRead)
async def get_current_merchant_profile(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns the profile of the authenticated active tenant."""
    merchant = await CoreService.get_merchant_by_id(db, UUID(tenant.merchant_id))
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant
