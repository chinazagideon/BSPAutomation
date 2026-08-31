"""Stage 2 Response Templates Bank for Custom Local Classifier Intents."""

from typing import Dict, Any, Optional


def synthesize_custom_model_reply(
    intent: str,
    dialect: str,
    entities: Dict[str, Any],
    merchant_name: str = "Enterprise SME Store",
) -> str:
    """Synthesizes a tone-matched Nigerian Pidgin / Commercial Slang reply for Stage 2 intents."""
    is_pidgin = dialect == "Nigerian Pidgin"
    location = entities.get("location", "your area")
    quantity = entities.get("quantity", "your order")

    templates = {
        "WHOLESALE_DISCOUNT_INQUIRY": (
            f"No wahala! For bulk wholesale orders of {quantity}, we give special SME tiered discounts + free dispatch within Lagos/Abuja. How many units you wan start with?"
            if is_pidgin
            else f"Thank you for your bulk inquiry! We offer wholesale discounts for orders of {quantity} with complimentary logistics. How many units would you like to reserve?"
        ),
        "DELIVERY_TIMELINE_INQUIRY": (
            f"Sharp dispatch guaranteed! 🚚 For delivery to {location}, our dispatch riders deliver same-day (within 3-5 hours in Lagos) and interstate waybill lands in 24-48 hours max."
            if is_pidgin
            else f"Express delivery guaranteed! For delivery to {location}, local orders arrive same-day and interstate shipments take 24–48 hours."
        ),
        "TRUST_VERIFICATION_PROOF": (
            f"100% Legit! 🛡️ We be verified Nigerian SME with RC corporate registration and over 5,000+ completed deliveries. See our catalog & customer reviews here: https://catalog.sme.ng/proof"
            if is_pidgin
            else f"We are a verified, RC-registered business with over 5,000+ fulfilled customer deliveries across Nigeria. View our credentials and reviews here: https://catalog.sme.ng/proof"
        ),
        "REQUEST_PAYMENT_DETAILS": (
            f"Sharp! Dedicated payment details don ready:\n🏦 Bank: *Moniepoint MFB*\nAcct Name: *{merchant_name}*\nAcct No: *9031842901*\n\nOnce you transfer, alert go confirm automatically!"
            if is_pidgin
            else f"Your checkout is ready:\n🏦 Bank: *Moniepoint MFB*\nAccount Name: *{merchant_name}*\nAccount Number: *9031842901*\n\nYour payment will be reconciled automatically upon transfer."
        ),
        "GENERAL_INQUIRY": (
            f"Well done! Welcome to {merchant_name}. How we fit serve your business today?"
            if is_pidgin
            else f"Welcome to {merchant_name}! How may we assist your business today?"
        ),
    }

    return templates.get(intent, templates["GENERAL_INQUIRY"])
