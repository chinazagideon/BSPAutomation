"""Pydantic v2 Schemas for Core Tenant Management, Authentication, and RBAC."""

from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime
from pydantic import EmailStr, Field

from app.core.response import CamelModel


# -----------------------------------------------------------------------------
# 1. MERCHANT TENANT SCHEMAS
# -----------------------------------------------------------------------------
class MerchantBase(CamelModel):
    business_name: str = Field(..., max_length=256)
    slug: str = Field(..., max_length=128)
    bsp_provider: str = Field("META_CLOUD", max_length=32)
    whatsapp_business_phone: str = Field(..., max_length=32)
    whatsapp_phone_number_id: Optional[str] = None
    default_currency: str = Field("NGN", min_length=3, max_length=3)
    variance_tolerance_kobo: int = Field(0, ge=0)
    anti_ghosting_hold_seconds: int = Field(600, ge=60)


class MerchantCreate(MerchantBase):
    pass


class MerchantRead(MerchantBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ResolvedChannelContext(CamelModel):
    """Immutable resolved tenant channel identity."""
    merchant_id: str
    channel_id: Optional[str] = None
    phone_number_id: str
    business_phone: Optional[str] = None
    provider: str = "META_CLOUD"
    channel_label: str = "Main Office"
    is_default: bool = False
    is_active: bool = True


# -----------------------------------------------------------------------------
# 2. USER & TEAM PROVISIONING SCHEMAS
# -----------------------------------------------------------------------------
class UserCreate(CamelModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    full_name: str = Field(..., max_length=256)
    role: Literal["ADMIN", "MANAGER", "AGENT", "READ_ONLY"] = "AGENT"


class UserRead(CamelModel):
    id: UUID
    merchant_id: UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# -----------------------------------------------------------------------------
# 3. ONBOARDING & AUTHENTICATION SCHEMAS
# -----------------------------------------------------------------------------
class MerchantRegisterRequest(CamelModel):
    """Atomic self-serve registration payload for Nigerian SME merchants."""
    business_name: str = Field(..., max_length=256)
    slug: str = Field(..., max_length=128)
    bsp_provider: Literal["META_CLOUD", "TERMII", "TWILIO_AFRICA", "INFOBIP_NG"] = "META_CLOUD"
    whatsapp_business_phone: str = Field(..., max_length=32)
    whatsapp_phone_number_id: Optional[str] = None
    default_currency: str = Field("NGN", min_length=3, max_length=3)
    variance_tolerance_kobo: int = Field(0, ge=0)
    anti_ghosting_hold_seconds: int = Field(600, ge=60)

    # Initial OWNER User Profile
    owner_email: EmailStr
    owner_password: str = Field(..., min_length=8)
    owner_full_name: str = Field(..., max_length=256)


class UserLogin(CamelModel):
    email: EmailStr
    password: str


class TokenRefreshRequest(CamelModel):
    refresh_token: str


class TokenResponse(CamelModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = Field(900, description="Access token expiration in seconds (15 min)")
    merchant_id: str
    user_id: str
    role: str
    full_name: str


class UserProfileResponse(CamelModel):
    user: UserRead
    merchant: MerchantRead
    role_rank: int
    active_channel: str


# -----------------------------------------------------------------------------
# 4. RFC 7807 PROBLEM DETAILS SCHEMA
# -----------------------------------------------------------------------------
class RFC7807ProblemDetails(CamelModel):
    type: str
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    trace_id: Optional[str] = None

