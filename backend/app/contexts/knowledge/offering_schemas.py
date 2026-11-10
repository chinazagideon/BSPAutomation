"""Core Offering Contract & Polymorphic Vertical Schemas (ADR-0044).

Universal base attributes (sku, title, price_kobo, currency, category, is_available)
paired with vertical-specific extensions (PHYSICAL_PRODUCT, SERVICE_APPOINTMENT).
"""

from enum import Enum
from typing import List, Optional, Dict, Any, Union, Annotated, Literal
from uuid import UUID, uuid5
from pydantic import BaseModel, Field, model_validator

OFFERING_UUID_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
DEFAULT_DEMO_MERCHANT_UUID = "00000000-0000-0000-0000-000000000001"


def compute_offering_id(merchant_id: Optional[Union[UUID, str]], sku: str) -> str:
    """Computes a deterministic, tenant-scoped UUIDv5 for a catalog offering."""
    scope = str(merchant_id).strip().lower() if merchant_id else DEFAULT_DEMO_MERCHANT_UUID
    norm_sku = (sku or "UNKNOWN").strip().upper()
    return str(uuid5(OFFERING_UUID_NAMESPACE, f"{scope}:{norm_sku}"))



class OfferingType(str, Enum):
    PHYSICAL_PRODUCT = "PHYSICAL_PRODUCT"
    SERVICE_APPOINTMENT = "SERVICE_APPOINTMENT"
    DIGITAL_GOOD = "DIGITAL_GOOD"


class BaseOfferingMetadata(BaseModel):
    sku: str = Field(..., description="Unique merchant SKU / identifier")
    category: str = Field(..., description="Normalized category tag (e.g. 'rice', 'sugar')")
    search_keywords: List[str] = Field(default_factory=list, description="Aliases, slang, common misspellings")
    price_kobo: int = Field(..., ge=0, description="Price in minor currency Kobo")
    currency: str = Field("NGN", max_length=3)
    is_available: bool = Field(True, description="Availability / stock status")


class PhysicalProductMetadata(BaseOfferingMetadata):
    offering_type: Literal[OfferingType.PHYSICAL_PRODUCT] = OfferingType.PHYSICAL_PRODUCT
    unit: str = Field("unit", description="e.g. 'bag', 'carton', 'pack'")
    weight: Optional[str] = Field(None, description="e.g. '50kg', '500g'")
    stock_quantity: int = Field(0, ge=0)
    min_order_qty: int = Field(1, ge=1)
    image_url: Optional[str] = None
    meta_catalog_id: Optional[str] = None


class ServiceAppointmentMetadata(BaseOfferingMetadata):
    offering_type: Literal[OfferingType.SERVICE_APPOINTMENT] = OfferingType.SERVICE_APPOINTMENT
    duration_minutes: int = Field(..., gt=0)
    commitment_deposit_kobo: int = Field(0, ge=0)
    resource_type: Optional[str] = None
    cancellation_notice_hours: int = Field(24, ge=0)


OfferingMetadata = Annotated[
    Union[PhysicalProductMetadata, ServiceAppointmentMetadata],
    Field(discriminator="offering_type"),
]


class CoreOfferingDTO(BaseModel):
    id: Optional[str] = None
    offering_id: str = ""
    merchant_id: Optional[str] = None
    sku: str
    title: str
    description: str
    offering_type: OfferingType = OfferingType.PHYSICAL_PRODUCT
    price_kobo: int = Field(..., ge=0)
    price_naira: float = Field(0.0, ge=0.0)
    currency: str = "NGN"
    is_available: bool = True
    category: str
    search_keywords: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def compute_price_naira_and_offering_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "price_naira" not in data or data["price_naira"] is None or data["price_naira"] == 0.0:
                kobo = data.get("price_kobo")
                if kobo is not None:
                    data["price_naira"] = round(kobo / 100.0, 2)
            elif "price_kobo" not in data or data["price_kobo"] is None:
                naira = data.get("price_naira", 0.0)
                data["price_kobo"] = int(naira * 100)

            sku = data.get("sku") or ""
            merchant_id = data.get("merchant_id")
            canonical_id = data.get("offering_id") or data.get("id")
            if not canonical_id or str(canonical_id).startswith("demo-"):
                canonical_id = compute_offering_id(merchant_id, sku)
            data["offering_id"] = str(canonical_id)
            if not data.get("id") or str(data.get("id")).startswith("demo-"):
                data["id"] = str(canonical_id)
        return data
