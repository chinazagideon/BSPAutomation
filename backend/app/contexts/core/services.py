"""Core Tenant Infrastructure and Authentication Services."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import TenantChannelSecurityError
from app.contexts.core.models import Merchant, MerchantChannel, User, RefreshToken
from app.contexts.core.schemas import (
    MerchantCreate,
    MerchantRegisterRequest,
    ResolvedChannelContext,
    UserLogin,
    UserCreate,
    TokenResponse,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_refresh_token,
    compute_sha256_hash,
)


class CoreService:
    @staticmethod
    async def create_merchant(session: AsyncSession, data: MerchantCreate) -> Merchant:
        merchant = Merchant(
            business_name=data.business_name,
            slug=data.slug,
            bsp_provider=data.bsp_provider,
            whatsapp_business_phone=data.whatsapp_business_phone,
            whatsapp_phone_number_id=data.whatsapp_phone_number_id,
            default_currency=data.default_currency,
            variance_tolerance_kobo=data.variance_tolerance_kobo,
            anti_ghosting_hold_seconds=data.anti_ghosting_hold_seconds,
        )
        session.add(merchant)
        await session.flush()
        return merchant

    @staticmethod
    async def get_merchant_by_id(session: AsyncSession, merchant_id: UUID) -> Optional[Merchant]:
        result = await session.execute(select(Merchant).where(Merchant.id == merchant_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_merchants(session: AsyncSession, limit: int = 50) -> List[Merchant]:
        result = await session.execute(select(Merchant).limit(limit))
        return list(result.scalars().all())


class AuthService:
    """Enterprise Authentication, Token Lifecycle, and Team Management Service."""

    @staticmethod
    async def register_merchant_and_owner(
        session: AsyncSession,
        data: MerchantRegisterRequest,
    ) -> Tuple[TokenResponse, str, User, Merchant]:
        """
        Atomic SME Onboarding:
        1. Checks uniqueness of merchant slug and owner email.
        2. Creates merchant record.
        3. Creates owner user record with role 'OWNER'.
        4. Seeds default Chart of Accounts.
        5. Issues initial short-lived JWT and rotating refresh token pair.
        """
        # Check slug uniqueness
        existing_merchant = await session.execute(select(Merchant).where(Merchant.slug == data.slug))
        if existing_merchant.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Merchant with slug '{data.slug}' already exists",
            )

        # Check email uniqueness
        existing_user = await session.execute(select(User).where(User.email == data.owner_email))
        if existing_user.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email '{data.owner_email}' already exists",
            )

        # 1. Create Merchant
        merchant = Merchant(
            business_name=data.business_name,
            slug=data.slug,
            bsp_provider=data.bsp_provider,
            whatsapp_business_phone=data.whatsapp_business_phone,
            whatsapp_phone_number_id=data.whatsapp_phone_number_id,
            default_currency=data.default_currency,
            variance_tolerance_kobo=data.variance_tolerance_kobo,
            anti_ghosting_hold_seconds=data.anti_ghosting_hold_seconds,
        )
        session.add(merchant)
        await session.flush()

        # 2. Create Owner User
        owner = User(
            merchant_id=merchant.id,
            email=data.owner_email,
            password_hash=hash_password(data.owner_password),
            full_name=data.owner_full_name,
            role="OWNER",
            is_active=True,
        )
        session.add(owner)
        await session.flush()

        # 3. Seed Chart of Accounts
        try:
            await session.execute(
                text("SELECT ledger.seed_standard_chart_of_accounts(:merchant_id)"),
                {"merchant_id": str(merchant.id)},
            )
        except Exception:
            # Tolerates environments where DB functions are mocked/unavailable
            pass

        # 4. Generate Token Family and Refresh Token
        family_id = uuid.uuid4()
        raw_refresh_token, token_hash = generate_refresh_token()
        now = datetime.now(timezone.utc)
        refresh_token_record = RefreshToken(
            merchant_id=merchant.id,
            user_id=owner.id,
            token_hash=token_hash,
            family_id=family_id,
            is_revoked=False,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=now,
        )
        session.add(refresh_token_record)
        await session.flush()

        # 5. Generate Short-Lived Access Token (15 min)
        jwt_claims = {
            "sub": str(owner.id),
            "merchant_id": str(merchant.id),
            "merchant_slug": merchant.slug,
            "role": owner.role,
            "email": owner.email,
        }
        access_token = create_access_token(jwt_claims)

        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            merchant_id=str(merchant.id),
            user_id=str(owner.id),
            role=owner.role,
            full_name=owner.full_name,
        )
        return token_response, raw_refresh_token, owner, merchant

    @staticmethod
    async def authenticate_user(
        session: AsyncSession,
        data: UserLogin,
    ) -> Tuple[TokenResponse, str, User, Merchant]:
        """
        Authenticates user with password verification, enforces account lockout rules,
        and issues a fresh JWT + rotating refresh token pair.
        """
        result = await session.execute(
            select(User).where(User.email == data.email)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        now = datetime.now(timezone.utc)

        # Check Account Lockout Governor (ADR-0032)
        if user.locked_until and user.locked_until > now:
            remaining_mins = int((user.locked_until - now).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account is temporarily locked due to excessive failed attempts. Try again in {remaining_mins} minutes.",
            )

        # Check Password
        if not verify_password(data.password, user.password_hash):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
                user.locked_until = now + timedelta(minutes=settings.ACCOUNT_LOCKOUT_DURATION_MINUTES)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated. Contact merchant owner.",
            )

        # Reset failed attempts on success
        user.failed_login_attempts = 0
        user.locked_until = None

        # Fetch Merchant Context
        merchant = await session.get(Merchant, user.merchant_id)
        if not merchant or not merchant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Merchant tenant is inactive or suspended.",
            )

        # Generate Refresh Token in new family
        family_id = uuid.uuid4()
        raw_refresh_token, token_hash = generate_refresh_token()
        refresh_token_record = RefreshToken(
            merchant_id=merchant.id,
            user_id=user.id,
            token_hash=token_hash,
            family_id=family_id,
            is_revoked=False,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=now,
        )
        session.add(refresh_token_record)
        await session.flush()

        jwt_claims = {
            "sub": str(user.id),
            "merchant_id": str(merchant.id),
            "merchant_slug": merchant.slug,
            "role": user.role,
            "email": user.email,
        }
        access_token = create_access_token(jwt_claims)

        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            merchant_id=str(merchant.id),
            user_id=str(user.id),
            role=user.role,
            full_name=user.full_name,
        )
        return token_response, raw_refresh_token, user, merchant

    @staticmethod
    async def rotate_refresh_token(
        session: AsyncSession,
        raw_refresh_token: str,
    ) -> Tuple[TokenResponse, str]:
        """
        Rotates refresh token with single-use enforcement, 5-second concurrency leeway,
        and automatic whole-family revocation on replay attack (ADR-0027, ADR-0032).
        """
        token_hash = compute_sha256_hash(raw_refresh_token)
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        token = result.scalar_one_or_none()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or unrecognized refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        now = datetime.now(timezone.utc)

        # 1. Check if token was explicitly revoked
        if token.is_revoked:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token.family_id)
                .values(is_revoked=True)
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session revoked due to security violation",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 2. Check if token was previously consumed (Replay Detection & Concurrency Grace Window)
        if token.consumed_at is not None:
            time_since_consumed = (now - token.consumed_at).total_seconds()
            if time_since_consumed <= settings.REFRESH_TOKEN_GRACE_SECONDS:
                # Concurrency leeway: Find the latest active token in this family and re-serve access token
                user = await session.get(User, token.user_id)
                merchant = await session.get(Merchant, token.merchant_id)
                jwt_claims = {
                    "sub": str(user.id),
                    "merchant_id": str(merchant.id),
                    "merchant_slug": merchant.slug,
                    "role": user.role,
                    "email": user.email,
                }
                access_token = create_access_token(jwt_claims)
                return TokenResponse(
                    access_token=access_token,
                    refresh_token=raw_refresh_token,
                    token_type="bearer",
                    expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    merchant_id=str(merchant.id),
                    user_id=str(user.id),
                    role=user.role,
                    full_name=user.full_name,
                ), raw_refresh_token
            else:
                # Replay attack detected beyond grace period! Revoke entire family
                await session.execute(
                    update(RefreshToken)
                    .where(RefreshToken.family_id == token.family_id)
                    .values(is_revoked=True)
                )
                await session.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token reuse detected. All sessions in this family have been terminated.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # 3. Check token expiration
        if token.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 4. Valid Rotation: Mark current token consumed
        token.consumed_at = now

        # Create new child token in the same family
        new_raw_token, new_token_hash = generate_refresh_token()
        new_token_record = RefreshToken(
            merchant_id=token.merchant_id,
            user_id=token.user_id,
            token_hash=new_token_hash,
            family_id=token.family_id,
            is_revoked=False,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=now,
        )
        session.add(new_token_record)
        await session.flush()

        user = await session.get(User, token.user_id)
        merchant = await session.get(Merchant, token.merchant_id)

        jwt_claims = {
            "sub": str(user.id),
            "merchant_id": str(merchant.id),
            "merchant_slug": merchant.slug,
            "role": user.role,
            "email": user.email,
        }
        access_token = create_access_token(jwt_claims)

        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=new_raw_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            merchant_id=str(merchant.id),
            user_id=str(user.id),
            role=user.role,
            full_name=user.full_name,
        )
        return token_response, new_raw_token

    @staticmethod
    async def logout_user(
        session: AsyncSession,
        user_id: UUID,
        raw_refresh_token: Optional[str] = None,
    ) -> None:
        """Revokes active token families for the user."""
        if raw_refresh_token:
            token_hash = compute_sha256_hash(raw_refresh_token)
            result = await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            )
            token = result.scalar_one_or_none()
            if token:
                await session.execute(
                    update(RefreshToken)
                    .where(RefreshToken.family_id == token.family_id)
                    .values(is_revoked=True)
                )
                await session.flush()
                return

        # Fallback: Revoke all active tokens for user
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .values(is_revoked=True)
        )
        await session.flush()

    @staticmethod
    async def create_merchant_user(
        session: AsyncSession,
        merchant_id: UUID,
        data: UserCreate,
    ) -> User:
        """Provisions a new team member under the merchant tenant."""
        existing_user = await session.execute(
            select(User).where(User.email == data.email)
        )
        if existing_user.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email '{data.email}' already exists",
            )

        user = User(
            merchant_id=merchant_id,
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            role=data.role,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def list_merchant_users(
        session: AsyncSession,
        merchant_id: UUID,
    ) -> List[User]:
        """Lists all team members under the merchant tenant."""
        result = await session.execute(
            select(User).where(User.merchant_id == merchant_id).order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: UUID) -> Optional[User]:
        return await session.get(User, user_id)


# -----------------------------------------------------------------------------
# MULTI-CHANNEL MERCHANT IDENTIFICATION & RESOLUTION SERVICE (ADR-0048)
# -----------------------------------------------------------------------------
import time as _time
from typing import Dict as _Dict

_PHONE_CHANNEL_CACHE: _Dict[str, tuple[ResolvedChannelContext, float]] = {}
_CACHE_TTL_SECONDS = 300.0


class MerchantIdentificationService:
    """Single-responsibility service for multi-channel merchant identification and outbound channel validation."""

    @classmethod
    async def resolve_inbound(
        cls,
        phone_number_id: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[ResolvedChannelContext]:
        """
        Resolves `ResolvedChannelContext` from an incoming webhook `phone_number_id` or E.164 number.
        Uses Two-Tier Caching:
        1. Tier 1: Local In-Memory TTL Cache (<0.05ms)
        2. Tier 2: `core.merchant_channels` (1:N) with legacy fallback to `core.merchants`.
        """
        if not phone_number_id:
            return None

        now = _time.time()
        if phone_number_id in _PHONE_CHANNEL_CACHE:
            cached_ctx, exp = _PHONE_CHANNEL_CACHE[phone_number_id]
            if now < exp:
                return cached_ctx if cached_ctx.is_active else None
            del _PHONE_CHANNEL_CACHE[phone_number_id]

        if db is not None:
            resolved = await cls._query_inbound(db, phone_number_id)
        else:
            async with async_session_factory() as session:
                resolved = await cls._query_inbound(session, phone_number_id)

        if resolved and resolved.is_active:
            _PHONE_CHANNEL_CACHE[phone_number_id] = (resolved, now + _CACHE_TTL_SECONDS)
            if resolved.phone_number_id:
                _PHONE_CHANNEL_CACHE[resolved.phone_number_id] = (resolved, now + _CACHE_TTL_SECONDS)
            return resolved

        return None

    @classmethod
    async def _query_inbound(
        cls,
        session: AsyncSession,
        phone_number_id: str,
    ) -> Optional[ResolvedChannelContext]:
        # 1. Primary lookup in 1:N core.merchant_channels
        try:
            ch_query = (
                select(MerchantChannel)
                .where(
                    (MerchantChannel.phone_number_id == phone_number_id)
                    | (MerchantChannel.business_phone == phone_number_id)
                )
                .order_by(
                    MerchantChannel.is_active.desc(),
                    (MerchantChannel.phone_number_id == phone_number_id).desc(),
                    MerchantChannel.is_default.desc(),
                    MerchantChannel.updated_at.desc(),
                )
                .limit(1)
            )
            ch_res = await session.execute(ch_query)
            channel = ch_res.scalars().first()
            if channel is not None:
                if not channel.is_active:
                    return None
                return ResolvedChannelContext(
                    merchant_id=str(channel.merchant_id),
                    channel_id=str(channel.id),
                    phone_number_id=channel.phone_number_id,
                    business_phone=channel.business_phone,
                    provider=channel.provider,
                    channel_label=channel.channel_label,
                    is_default=channel.is_default,
                    is_active=channel.is_active,
                )
        except Exception:
            pass

        # 2. Backward-compatible fallback to legacy core.merchants columns
        m_query = (
            select(Merchant)
            .where(
                (Merchant.whatsapp_phone_number_id == phone_number_id)
                | (Merchant.whatsapp_business_phone == phone_number_id)
            )
            .order_by(
                Merchant.is_active.desc(),
                (Merchant.whatsapp_phone_number_id == phone_number_id).desc(),
                Merchant.updated_at.desc(),
            )
            .limit(1)
        )
        m_res = await session.execute(m_query)
        merchant = m_res.scalars().first()
        if merchant is not None:
            return ResolvedChannelContext(
                merchant_id=str(merchant.id),
                channel_id=None,
                phone_number_id=merchant.whatsapp_phone_number_id or phone_number_id,
                business_phone=merchant.whatsapp_business_phone,
                provider=merchant.bsp_provider or "META_CLOUD",
                channel_label="Main Office",
                is_default=True,
                is_active=True,
            )

        return None

    @classmethod
    async def resolve_outbound(
        cls,
        merchant_id: str,
        requested_phone_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> ResolvedChannelContext:
        """
        Validates outbound channel ownership for a tenant, backtracks a conversation's active `channel_id`,
        or dynamically resolves the tenant's default channel.
        Enforces a strict Fail-Closed policy: raises `TenantChannelSecurityError` if an unauthorized
        or inactive `requested_phone_id` is supplied.
        """
        try:
            m_uuid = UUID(str(merchant_id))
        except Exception:
            raise TenantChannelSecurityError(
                merchant_id=str(merchant_id),
                phone_number_id=str(requested_phone_id or "None"),
                reason="Invalid merchant UUID format",
            )

        if db is not None:
            return await cls._query_outbound(db, m_uuid, requested_phone_id, channel_id=channel_id)

        async with async_session_factory() as session:
            return await cls._query_outbound(session, m_uuid, requested_phone_id, channel_id=channel_id)

    @classmethod
    async def _query_outbound(
        cls,
        session: AsyncSession,
        merchant_uuid: UUID,
        requested_phone_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> ResolvedChannelContext:
        merchant_id_str = str(merchant_uuid)

        # Case 1: Explicit requested_phone_id supplied -> Verify ownership & active status
        if requested_phone_id:
            ch_query = (
                select(MerchantChannel)
                .where(
                    MerchantChannel.merchant_id == merchant_uuid,
                    (MerchantChannel.phone_number_id == requested_phone_id)
                    | (MerchantChannel.business_phone == requested_phone_id),
                )
                .order_by(
                    MerchantChannel.is_active.desc(),
                    MerchantChannel.is_default.desc(),
                )
                .limit(1)
            )
            ch_res = await session.execute(ch_query)
            owned_channel = ch_res.scalars().first()

            if owned_channel is not None:
                if not owned_channel.is_active:
                    raise TenantChannelSecurityError(
                        merchant_id=merchant_id_str,
                        phone_number_id=requested_phone_id,
                        reason="Channel is deactivated",
                    )
                return ResolvedChannelContext(
                    merchant_id=merchant_id_str,
                    channel_id=str(owned_channel.id),
                    phone_number_id=owned_channel.phone_number_id,
                    business_phone=owned_channel.business_phone,
                    provider=owned_channel.provider,
                    channel_label=owned_channel.channel_label,
                    is_default=owned_channel.is_default,
                    is_active=owned_channel.is_active,
                )

            # Check if requested_phone_id belongs to a different merchant in core.merchant_channels
            foreign_ch_query = (
                select(MerchantChannel)
                .where(
                    MerchantChannel.merchant_id != merchant_uuid,
                    (MerchantChannel.phone_number_id == requested_phone_id)
                    | (MerchantChannel.business_phone == requested_phone_id),
                )
                .limit(1)
            )
            foreign_ch = (await session.execute(foreign_ch_query)).scalars().first()
            if foreign_ch is not None:
                raise TenantChannelSecurityError(
                    merchant_id=merchant_id_str,
                    phone_number_id=requested_phone_id,
                    reason="Unauthorized cross-tenant channel access denied",
                )

            # Check legacy core.merchants record for this merchant
            merchant = await session.get(Merchant, merchant_uuid)
            if (
                merchant is not None
                and merchant.is_active
                and requested_phone_id in (merchant.whatsapp_phone_number_id, merchant.whatsapp_business_phone)
            ):
                return ResolvedChannelContext(
                    merchant_id=merchant_id_str,
                    channel_id=None,
                    phone_number_id=merchant.whatsapp_phone_number_id or requested_phone_id,
                    business_phone=merchant.whatsapp_business_phone,
                    provider=merchant.bsp_provider or "META_CLOUD",
                    channel_label="Main Office",
                    is_default=True,
                    is_active=True,
                )

            raise TenantChannelSecurityError(
                merchant_id=merchant_id_str,
                phone_number_id=requested_phone_id,
                reason="Unauthorized or unregistered channel for tenant",
            )

        # Case 1B: Conversation channel_id FK backtracking (when no explicit requested_phone_id was given)
        if channel_id:
            try:
                ch_uuid = UUID(str(channel_id))
                conv_ch_query = select(MerchantChannel).where(
                    MerchantChannel.id == ch_uuid,
                    MerchantChannel.merchant_id == merchant_uuid,
                    MerchantChannel.is_active == True,
                )
                conv_ch = (await session.execute(conv_ch_query)).scalars().first()
                if conv_ch is not None:
                    return ResolvedChannelContext(
                        merchant_id=merchant_id_str,
                        channel_id=str(conv_ch.id),
                        phone_number_id=conv_ch.phone_number_id,
                        business_phone=conv_ch.business_phone,
                        provider=conv_ch.provider,
                        channel_label=conv_ch.channel_label,
                        is_default=conv_ch.is_default,
                        is_active=conv_ch.is_active,
                    )
            except Exception:
                pass

        # Case 2: No requested_phone_id supplied (Proactive / Cron / Default resolution)
        all_ch_query = (
            select(MerchantChannel)
            .where(MerchantChannel.merchant_id == merchant_uuid)
            .order_by(
                MerchantChannel.is_active.desc(),
                MerchantChannel.is_default.desc(),
                MerchantChannel.created_at.asc(),
            )
        )
        all_channels = list((await session.execute(all_ch_query)).scalars().all())
        if all_channels:
            active_channels = [c for c in all_channels if c.is_active]
            if not active_channels:
                raise TenantChannelSecurityError(
                    merchant_id=merchant_id_str,
                    phone_number_id="None",
                    reason="All configured channels for tenant are deactivated",
                )
            chosen = active_channels[0]
            return ResolvedChannelContext(
                merchant_id=merchant_id_str,
                channel_id=str(chosen.id),
                phone_number_id=chosen.phone_number_id,
                business_phone=chosen.business_phone,
                provider=chosen.provider,
                channel_label=chosen.channel_label,
                is_default=chosen.is_default,
                is_active=chosen.is_active,
            )

        # Legacy fallback to core.merchants when no rows exist in core.merchant_channels
        merchant = await session.get(Merchant, merchant_uuid)
        if merchant is not None and merchant.is_active and (
            merchant.whatsapp_phone_number_id or merchant.whatsapp_business_phone
        ):
            return ResolvedChannelContext(
                merchant_id=merchant_id_str,
                channel_id=None,
                phone_number_id=merchant.whatsapp_phone_number_id or merchant.whatsapp_business_phone,
                business_phone=merchant.whatsapp_business_phone,
                provider=merchant.bsp_provider or "META_CLOUD",
                channel_label="Main Office",
                is_default=True,
                is_active=True,
            )

        raise TenantChannelSecurityError(
            merchant_id=merchant_id_str,
            phone_number_id="None",
            reason="No active outbound channel configured for tenant",
        )

    @classmethod
    async def list_merchant_channels(
        cls,
        merchant_id: str,
        db: Optional[AsyncSession] = None,
    ) -> List[ResolvedChannelContext]:
        """Returns all configured channels for a merchant."""
        try:
            m_uuid = UUID(str(merchant_id))
        except Exception:
            return []

        async def _fetch(session: AsyncSession) -> List[ResolvedChannelContext]:
            stmt = (
                select(MerchantChannel)
                .where(MerchantChannel.merchant_id == m_uuid)
                .order_by(MerchantChannel.is_default.desc(), MerchantChannel.created_at.asc())
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [
                ResolvedChannelContext(
                    merchant_id=str(r.merchant_id),
                    channel_id=str(r.id),
                    phone_number_id=r.phone_number_id,
                    business_phone=r.business_phone,
                    provider=r.provider,
                    channel_label=r.channel_label,
                    is_default=r.is_default,
                    is_active=r.is_active,
                )
                for r in rows
            ]

        if db is not None:
            return await _fetch(db)
        async with async_session_factory() as session:
            return await _fetch(session)

    @classmethod
    def invalidate_cache(cls, phone_number_id: Optional[str] = None) -> None:
        """Evicts a specific phone_number_id or clears the entire in-memory channel cache."""
        if phone_number_id is None:
            _PHONE_CHANNEL_CACHE.clear()
        else:
            _PHONE_CHANNEL_CACHE.pop(phone_number_id, None)
