"""Declarative Seed Data Definitions for Multi-Vertical Testing (ADR-0044).

Defines deterministic merchants, physical products, service appointments,
Nigerian Pidgin slang aliases, and out-of-stock fixtures.
"""

from typing import Dict, Any, List
from uuid import UUID

from app.contexts.knowledge.offering_schemas import OfferingType

# Deterministic UUIDv5 / Fixed UUIDs for test reproducibility
ALABA_AGRO_MERCHANT_ID = UUID("018f6c5a-8b1e-7230-a890-111111111111")
LEKKI_GLOW_MERCHANT_ID = UUID("018f6c5a-8b1e-7230-a890-222222222222")
HORIZON_TECH_MERCHANT_ID = UUID("018f6c5a-8b1e-7230-a890-333333333333")

DEMO_MERCHANTS: List[Dict[str, Any]] = [
    {
        "id": ALABA_AGRO_MERCHANT_ID,
        "business_name": "Alaba Agro & Commodities Depot",
        "slug": "alaba-agro",
        "whatsapp_business_phone": "+2348011223301",
        "whatsapp_phone_number_id": "meta_phone_alaba_agro",
        "channels": [
            {
                "phone_number_id": "meta_phone_alaba_agro",
                "business_phone": "+2348011223301",
                "provider": "META_CLOUD",
                "channel_label": "Main Retail Desk",
                "is_default": True,
                "is_active": True,
            },
            {
                "phone_number_id": "meta_phone_alaba_agro_delivery",
                "business_phone": "+2348011223399",
                "provider": "META_CLOUD",
                "channel_label": "Wholesale & Logistics Desk",
                "is_default": False,
                "is_active": True,
            },
        ],
    },
    {
        "id": LEKKI_GLOW_MERCHANT_ID,
        "business_name": "Lekki Glow Wellness & Barber Hub",
        "slug": "lekki-glow",
        "whatsapp_business_phone": "+2348011223302",
        "whatsapp_phone_number_id": "meta_phone_lekki_glow",
        "channels": [
            {
                "phone_number_id": "meta_phone_lekki_glow",
                "business_phone": "+2348011223302",
                "provider": "META_CLOUD",
                "channel_label": "Main Wellness Reception",
                "is_default": True,
                "is_active": True,
            },
        ],
    },
    {
        "id": HORIZON_TECH_MERCHANT_ID,
        "business_name": "Horizon Tech Gadgets Canary",
        "slug": "horizon-tech",
        "whatsapp_business_phone": "+2348011223303",
        "whatsapp_phone_number_id": "meta_phone_horizon_tech",
        "channels": [
            {
                "phone_number_id": "meta_phone_horizon_tech",
                "business_phone": "+2348011223303",
                "provider": "META_CLOUD",
                "channel_label": "Main Sales Line",
                "is_default": True,
                "is_active": True,
            },
        ],
    },
]

# -----------------------------------------------------------------------------
# 1. ALABA AGRO (COMMODITIES, GRAINS, PACKAGING VARIANTS, SLANG & OUT-OF-STOCK)
# -----------------------------------------------------------------------------
ALABA_AGRO_OFFERINGS: List[Dict[str, Any]] = [
    {
        "sku": "RICE_MAMA_GOLD_50KG",
        "title": "Mama Gold Rice 50kg",
        "content": "Premium parboiled Nigerian rice, 50kg full bag. Clean stone-free.",
        "category": "rice",
        "search_keywords": ["mama gold", "rice", "50kg", "shinkafa", "parboiled", "bag"],
        "price_kobo": 7800000,
        "price_naira": 78000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 25,
    },
    {
        "sku": "RICE_MAMA_GOLD_25KG",
        "title": "Mama Gold Rice 25kg",
        "content": "Half bag parboiled Nigerian rice, 25kg bag. Ideal for small families.",
        "category": "rice",
        "search_keywords": ["mama gold", "rice", "25kg", "shinkafa", "half bag"],
        "price_kobo": 4100000,
        "price_naira": 41000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "bag",
        "weight": "25kg",
        "stock_quantity": 40,
    },
    {
        "sku": "RICE_ROYAL_STALLION_50KG",
        "title": "Royal Stallion Rice 50kg",
        "content": "Imported high quality fragrant rice, 50kg full bag.",
        "category": "rice",
        "search_keywords": ["royal stallion", "stallion", "rice", "50kg", "shinkafa"],
        "price_kobo": 8000000,
        "price_naira": 80000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 15,
    },
    {
        "sku": "SUGAR_DANGOTE_50KG",
        "title": "Dangote Sugar 50kg",
        "content": "Refined pure white granulated sugar from Dangote, 50kg bag.",
        "category": "sugar",
        "search_keywords": ["dangote", "sugar", "50kg", "granulated", "suga", "bag"],
        "price_kobo": 8400000,
        "price_naira": 84000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 30,
    },
    {
        "sku": "SUGAR_ST_LOUIS_500G",
        "title": "St. Louis Sugar Cube (500g Box)",
        "content": "Classic French cube sugar, 500g retail box.",
        "category": "sugar",
        "search_keywords": ["st louis", "st. louis", "sugar", "cube", "500g", "box", "pack"],
        "price_kobo": 180000,
        "price_naira": 1800.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "box",
        "weight": "500g",
        "stock_quantity": 150,
    },
    {
        "sku": "OIL_DEVONS_KING_25L",
        "title": "Devon's King Vegetable Oil 25L",
        "content": "Pure cholesterol-free refined vegetable cooking oil in 25-litre yellow jerrycan.",
        "category": "oil",
        "search_keywords": ["ororo", "vegetable oil", "king's", "devon", "cooking oil", "25l", "jerrycan"],
        "price_kobo": 5800000,
        "price_naira": 58000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "jerrycan",
        "weight": "25L",
        "stock_quantity": 20,
    },
    {
        "sku": "FLOUR_GOLDEN_PENNY_50KG",
        "title": "Golden Penny Flour 50kg",
        "content": "All-purpose premium baking flour for bakeries, 50kg bag. (Currently sold out).",
        "category": "flour",
        "search_keywords": ["golden penny", "flour", "baking", "50kg", "dough"],
        "price_kobo": 6200000,
        "price_naira": 62000.0,
        "currency": "NGN",
        "is_available": False,  # Explicitly out-of-stock fixture
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "bag",
        "weight": "50kg",
        "stock_quantity": 0,
    },
]

# -----------------------------------------------------------------------------
# 2. LEKKI GLOW (WELLNESS, SERVICE APPOINTMENTS, DURATION, COMMITMENT DEPOSITS)
# -----------------------------------------------------------------------------
LEKKI_GLOW_OFFERINGS: List[Dict[str, Any]] = [
    {
        "sku": "SRV_EXECUTIVE_HAIRCUT",
        "title": "Executive Haircut & Beard Grooming",
        "content": "Precision skin fade, hot towel shave, beard wash, and scalp rejuvenation.",
        "category": "barber",
        "search_keywords": ["cut", "haircut", "fade", "beard", "barber", "grooming", "trim"],
        "price_kobo": 1500000,
        "price_naira": 15000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.SERVICE_APPOINTMENT.value,
        "duration_minutes": 45,
        "commitment_deposit_kobo": 500000,  # ₦5,000 commitment deposit
        "resource_type": "VIP_CHAIR",
        "cancellation_notice_hours": 12,
    },
    {
        "sku": "SRV_DEEP_TISSUE_MASSAGE",
        "title": "Deep Tissue Swedish Massage (60 Mins)",
        "content": "Full body therapeutic deep tissue stress relief massage with organic aromatherapy oils.",
        "category": "spa",
        "search_keywords": ["massage", "spa", "relaxation", "deep tissue", "swedish"],
        "price_kobo": 3500000,
        "price_naira": 35000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.SERVICE_APPOINTMENT.value,
        "duration_minutes": 60,
        "commitment_deposit_kobo": 1000000,  # ₦10,000 commitment deposit
        "resource_type": "MASSAGE_SUITE",
        "cancellation_notice_hours": 24,
    },
    {
        "sku": "SRV_BRIDAL_GLOW_FACIAL",
        "title": "Bridal Radiance Glow Facial (90 Mins)",
        "content": "Hydrating multi-layer botanical facial with collagen infusion and light therapy.",
        "category": "skincare",
        "search_keywords": ["facial", "skincare", "glow", "bridal", "beauty"],
        "price_kobo": 5000000,
        "price_naira": 50000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.SERVICE_APPOINTMENT.value,
        "duration_minutes": 90,
        "commitment_deposit_kobo": 1500000,  # ₦15,000 commitment deposit
        "resource_type": "DERMA_SUITE",
        "cancellation_notice_hours": 48,
    },
    {
        "sku": "PROD_ORGANIC_BEARD_OIL",
        "title": "Lekki Glow Organic Argan Beard Oil (50ml)",
        "content": "Cold-pressed Moroccan argan and jojoba beard conditioning oil.",
        "category": "grooming",
        "search_keywords": ["beard oil", "organic", "argan", "beard", "oil"],
        "price_kobo": 850000,
        "price_naira": 8500.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "bottle",
        "weight": "50ml",
        "stock_quantity": 50,
    },
]

# -----------------------------------------------------------------------------
# 3. HORIZON TECH (GADGETS & COMPETITOR ISOLATION CANARY)
# -----------------------------------------------------------------------------
HORIZON_TECH_OFFERINGS: List[Dict[str, Any]] = [
    {
        "sku": "TECH_IPHONE_15_PRO_128GB",
        "title": "Apple iPhone 15 Pro 128GB Natural Titanium",
        "content": "Brand new sealed Apple iPhone 15 Pro, 128GB storage, 1-year Apple care warranty.",
        "category": "phones",
        "search_keywords": ["iphone", "iphone 15", "apple", "phone", "gadget"],
        "price_kobo": 145000000,
        "price_naira": 1450000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "unit",
        "stock_quantity": 5,
    },
    {
        "sku": "TECH_ANKER_POWERBANK_20K",
        "title": "Anker PowerCore 20,000mAh PD Fast Charger",
        "content": "High-capacity portable power bank with 20W USB-C Power Delivery fast charging.",
        "category": "accessories",
        "search_keywords": ["anker", "powerbank", "charger", "battery", "fast charger"],
        "price_kobo": 3800000,
        "price_naira": 38000.0,
        "currency": "NGN",
        "is_available": True,
        "offering_type": OfferingType.PHYSICAL_PRODUCT.value,
        "unit": "unit",
        "stock_quantity": 25,
    },
]
