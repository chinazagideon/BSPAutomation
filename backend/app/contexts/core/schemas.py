"""Pydantic v2 Schemas for Core Tenant Management and Authentication."""

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class MerchantBase(BaseModel):
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

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    merchant_id: str
    user_id: str
    role: str
    full_name: str
