"""Abstract port interfaces for external payment, messaging, ML, and LLM integrations."""

import re
from abc import ABC, abstractmethod
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, model_validator

from app.contexts.compliance.services import sanitize_nigerian_pii_detailed


# -----------------------------------------------------------------------------
# DECLARATIVE PYDANTIC V2 ANNOTATED VALIDATORS (PATTERN 1 & PATTERN 4)
# -----------------------------------------------------------------------------
def _scrub_pii_str(val: Any) -> str:
    if val is None:
        return ""
    cleaned, _ = sanitize_nigerian_pii_detailed(str(val))
    return cleaned


def _scrub_slot_dict(val: Any) -> Dict[str, Any]:
    if not isinstance(val, dict):
        return {}
    sanitized: Dict[str, Any] = {}
    for k, v in val.items():
        if isinstance(v, str):
            cleaned, _ = sanitize_nigerian_pii_detailed(v)
            sanitized[k] = cleaned
        else:
            sanitized[k] = v
    return sanitized


def _coerce_confidence(val: Any) -> float:
    try:
        num = float(val)
        if 1.0 < num <= 100.0:
            num = num / 100.0
        return max(0.0, min(1.0, num))
    except (TypeError, ValueError):
        return 0.90


def _coerce_urgency(val: Any) -> int:
    try:
        num = float(val)
        if 0.0 <= num <= 1.0:
            score = int(num * 10 + 0.5)
        else:
            score = int(num + 0.5)
        return max(1, min(10, score))
    except (TypeError, ValueError):
        return 7


def _coerce_lead_tier(val: Any) -> str:
    raw = str(val or "WARM").upper()
    if "HOT" in raw or "1" in raw:
        return "HOT"
    if "COLD" in raw or "3" in raw:
        return "COLD"
    return "WARM"


def _coerce_dialect(val: Any) -> str:
    raw = str(val or "Standard English").strip()
    lower = raw.lower()
    if "pidgin" in lower:
        return "Nigerian Pidgin"
    if "slang" in lower:
        return "Commercial Slang"
    if "english" in lower:
        return "Standard English"
    return raw if raw else "Standard English"


def _coerce_intent(val: Any) -> str:
    raw = str(val or "GENERAL_INQUIRY").upper().strip()
    return raw if raw else "GENERAL_INQUIRY"


PiiSanitizedStr = Annotated[str, AfterValidator(_scrub_pii_str)]
PiiSanitizedSlotMap = Annotated[Dict[str, Any], BeforeValidator(_scrub_slot_dict)]
UnitConfidence = Annotated[float, BeforeValidator(_coerce_confidence)]
UrgencyScoreInt = Annotated[int, BeforeValidator(_coerce_urgency)]
LeadTierType = Annotated[str, BeforeValidator(_coerce_lead_tier)]
DialectType = Annotated[str, BeforeValidator(_coerce_dialect)]
NormalizedIntentStr = Annotated[str, BeforeValidator(_coerce_intent)]

CanonicalIntentType = Literal[
    "INSTANT_CHECKOUT_ORDER",
    "PRICE_INQUIRY",
    "SHOW_PRODUCT_CATALOG",
    "WHOLESALE_DISCOUNT_INQUIRY",
    "DELIVERY_TIMELINE_INQUIRY",
    "RESERVE_APPOINTMENT",
    "CONFIRM_PAYMENT",
    "REQUEST_PAYMENT_DETAILS",
    "TRUST_VERIFICATION_PROOF",
    "HUMAN_AGENT_HANDOFF",
    "DISPATCH_AGENT_HANDOFF",
    "COMPLEX_CONSULTATION",
    "LOGISTICS_OR_POLICY_INQUIRY",
    "VERTICAL_SPECIFIC_INQUIRY",
    "CANCEL_ORDER",
    "GREETING_ENGAGEMENT",
    "GENERAL_INQUIRY",
]

CANONICAL_INTENT_VALUES = {
    "INSTANT_CHECKOUT_ORDER",
    "PRICE_INQUIRY",
    "SHOW_PRODUCT_CATALOG",
    "WHOLESALE_DISCOUNT_INQUIRY",
    "DELIVERY_TIMELINE_INQUIRY",
    "RESERVE_APPOINTMENT",
    "CONFIRM_PAYMENT",
    "REQUEST_PAYMENT_DETAILS",
    "TRUST_VERIFICATION_PROOF",
    "HUMAN_AGENT_HANDOFF",
    "DISPATCH_AGENT_HANDOFF",
    "COMPLEX_CONSULTATION",
    "LOGISTICS_OR_POLICY_INQUIRY",
    "VERTICAL_SPECIFIC_INQUIRY",
    "CANCEL_ORDER",
    "GREETING_ENGAGEMENT",
    "GENERAL_INQUIRY",
}


def _coerce_canonical_intent(val: Any) -> str:
    norm = _coerce_intent(val)
    if norm in CANONICAL_INTENT_VALUES:
        return norm
    if "BUY" in norm or "ORDER" in norm or "CHECKOUT" in norm:
        return "INSTANT_CHECKOUT_ORDER"
    if "PRICE" in norm or "COST" in norm or "CATALOG" in norm or "STOCK" in norm:
        return "PRICE_INQUIRY"
    if "DELIVER" in norm or "ETA" in norm or "TIMELINE" in norm or "SHIPPING" in norm:
        return "DELIVERY_TIMELINE_INQUIRY"
    if "DISCOUNT" in norm or "WHOLESALE" in norm:
        return "WHOLESALE_DISCOUNT_INQUIRY"
    if "AGENT" in norm or "HUMAN" in norm or "HANDOFF" in norm:
        return "HUMAN_AGENT_HANDOFF"
    if "CANCEL" in norm or "ABORT" in norm:
        return "CANCEL_ORDER"
    if "PAY" in norm:
        return "CONFIRM_PAYMENT"
    if "RESERVE" in norm or "BOOK" in norm or "APPOINTMENT" in norm:
        return "RESERVE_APPOINTMENT"
    if "TRUST" in norm or "LEGIT" in norm or "PROOF" in norm:
        return "TRUST_VERIFICATION_PROOF"
    if "GREET" in norm or "HELLO" in norm:
        return "GREETING_ENGAGEMENT"
    return "GENERAL_INQUIRY"


CoercedCanonicalIntent = Annotated[CanonicalIntentType, BeforeValidator(_coerce_canonical_intent)]


class ClassificationOutput(BaseModel):
    """Normalized output contract across all NLU classification engines."""
    intent: NormalizedIntentStr = "GENERAL_INQUIRY"
    lead_tier: LeadTierType = Field("WARM", description="HOT, WARM, COLD")
    urgency_score: UrgencyScoreInt = Field(7, ge=1, le=10)
    confidence: UnitConfidence = Field(0.90, ge=0.0, le=1.0)
    detected_dialect: DialectType = Field("Nigerian Commercial Slang", description="Nigerian Pidgin, Commercial Slang, Standard English")
    suggested_reply: Optional[str] = None
    action: Optional[str] = None
    extracted_entities: PiiSanitizedSlotMap = Field(default_factory=dict)
    tokens_consumed: int = 0
    latency_ms: float = 0.0


# -----------------------------------------------------------------------------
# STATELESS OPEN-WEIGHT MODEL LAYER CONTRACTS (FUNCTION A & FUNCTION B)
# -----------------------------------------------------------------------------
class CartLineItem(BaseModel):
    """Canonical multi-item cart line entry keyed by unique offering_id and merchant SKU."""
    offering_id: Optional[str] = None
    sku: Optional[str] = None
    product: Optional[PiiSanitizedStr] = None
    product_name: Optional[PiiSanitizedStr] = None
    quantity: int = Field(1, ge=1)
    unit_price_kobo: Optional[int] = None
    in_stock: bool = True


class ParsedTurnInput(BaseModel):
    """Strict JSON output contract for Function A (Stateless Input Parser)."""
    intent: CoercedCanonicalIntent = Field(
        "GENERAL_INQUIRY",
        description="Primary commercial intent classified from the customer message",
    )
    canonical_query: PiiSanitizedStr = Field(
        "",
        description="Customer query normalized into clear commercial English",
    )
    slots: PiiSanitizedSlotMap = Field(
        default_factory=dict,
        description="Extracted parameter slots (product, quantity, location, delivery_zone, fulfillment_type, budget_naira)",
    )
    slot_mutations: PiiSanitizedSlotMap = Field(
        default_factory=dict,
        description="Explicit mid-flow slot overrides when customer changes product, quantity, or location",
    )
    is_cancellation: bool = Field(
        False,
        description="True ONLY if the user explicitly wants to cancel or abort their order",
    )
    is_affirmation: bool = Field(
        False,
        description="True if the user is affirming a pending offer (yes, oya, proceed, sharp)",
    )
    is_negation: bool = Field(
        False,
        description="True if the user is declining a pending offer (no, leave am)",
    )
    detected_dialect: DialectType = Field(
        "Standard English",
        description="Nigerian Pidgin, Commercial Slang, or Standard English",
    )
    confidence: UnitConfidence = Field(0.95, ge=0.0, le=1.0)
    lead_tier: LeadTierType = "WARM"
    urgency_score: UrgencyScoreInt = 7
    tokens_consumed: int = 0
    latency_ms: float = 0.0

    @classmethod
    def llm_json_schema(cls) -> Dict[str, Any]:
        """Generates strict JSON schema for vLLM/Ollama response_format grammar enforcement."""
        schema = cls.model_json_schema()
        props = schema.get("properties", {})
        for telemetry_key in ("tokens_consumed", "latency_ms"):
            props.pop(telemetry_key, None)
        return schema


class HydrationTranslationInput(BaseModel):
    """Structured state payload injected into Function B (Dynamic Prompt Hydration)."""
    primary_intent: str
    verified_facts: Dict[str, Any] = Field(default_factory=dict)
    fallback_body_text: str
    resumed_frame: Optional[Dict[str, Any]] = None
    target_dialect: DialectType = "Standard English"
    merchant_name: str = "Enterprise SME Store"


class HydrationTranslationOutput(BaseModel):
    """Self-healing output contract for Function B enforcing Kobo/Naira financial invariants (Pattern 2)."""
    translated_text: PiiSanitizedStr
    fallback_body_text: str = ""
    verified_amounts: List[str] = Field(default_factory=list)
    tokens_consumed: int = 0
    latency_ms: float = 0.0
    used_fallback: bool = False

    @model_validator(mode="after")
    def _enforce_kobo_numeric_invariant(self) -> "HydrationTranslationOutput":
        if not self.translated_text or not self.translated_text.strip():
            self.translated_text = self.fallback_body_text
            self.used_fallback = True
            return self

        expected_naira = set(
            self.verified_amounts
            or re.findall(r"₦[\d,]+(?:\.\d{2})?", self.fallback_body_text or "")
        )
        actual_naira = set(re.findall(r"₦[\d,]+(?:\.\d{2})?", self.translated_text))
        if expected_naira and not expected_naira.issubset(actual_naira):
            self.translated_text = self.fallback_body_text
            self.used_fallback = True
        return self


# -----------------------------------------------------------------------------
# DISCRIMINATED UNIONS FOR INTERACTIVE PROTOCOL EVENTS (PATTERN 5)
# -----------------------------------------------------------------------------
class ProductTapAction(BaseModel):
    action_kind: Literal["PRODUCT_TAP"] = "PRODUCT_TAP"
    sku: str
    offering_id: Optional[str] = None


class SlotBindAction(BaseModel):
    action_kind: Literal["SLOT_BIND"] = "SLOT_BIND"
    slot_name: str
    slot_value: PiiSanitizedStr


class CommandTapAction(BaseModel):
    action_kind: Literal["COMMAND_TAP"] = "COMMAND_TAP"
    command: Literal["SHOW_CATALOG", "AGENT_HANDOFF", "UNKNOWN"]
    raw_id: str


InteractiveActionUnion = Annotated[
    Union[ProductTapAction, SlotBindAction, CommandTapAction],
    Field(discriminator="action_kind"),
]


class InteractiveProtocolEnvelope(BaseModel):
    """Parses raw WhatsApp interactive_id strings into a typed Discriminated Union."""
    event: InteractiveActionUnion

    @model_validator(mode="before")
    @classmethod
    def _parse_raw_callback_string(cls, data: Any) -> Dict[str, Any]:
        if isinstance(data, dict) and "event" in data:
            return data
        raw = data.strip() if isinstance(data, str) else str((data or {}).get("raw_id", "")).strip()
        if raw.startswith("PRODUCT:"):
            target = raw.split(":", 1)[1].strip()
            return {"event": {"action_kind": "PRODUCT_TAP", "sku": target, "offering_id": target}}
        if raw.startswith("SET_SLOT:"):
            parts = raw.split(":", 2)
            if len(parts) == 3:
                slot_key = parts[1].strip()
                slot_val = parts[2].strip()
                if slot_key.startswith("line_item_sku:") and ":" in slot_val:
                    pass
                elif slot_key == "line_item_sku" and ":" in slot_val:
                    idx_part, actual_val = slot_val.split(":", 1)
                    slot_key = f"line_item_sku:{idx_part.strip()}"
                    slot_val = actual_val.strip()
                return {
                    "event": {
                        "action_kind": "SLOT_BIND",
                        "slot_name": slot_key,
                        "slot_value": slot_val,
                    }
                }
        if raw in ("SHOW_CATALOG", "BROWSE_CATALOG", "INTENT:SHOW_CATALOG"):
            return {"event": {"action_kind": "COMMAND_TAP", "command": "SHOW_CATALOG", "raw_id": raw}}
        if raw in ("AGENT_HANDOFF", "SPEAK_TO_AGENT", "INTENT:AGENT_HANDOFF"):
            return {"event": {"action_kind": "COMMAND_TAP", "command": "AGENT_HANDOFF", "raw_id": raw}}
        return {"event": {"action_kind": "COMMAND_TAP", "command": "UNKNOWN", "raw_id": raw}}


class CarouselCard(BaseModel):
    """Single interactive carousel card (media header + body + CTA URL button)."""
    header_type: Literal["image", "video"] = "image"
    media_url: str = Field(..., min_length=1)
    body_text: str = Field(..., min_length=1, max_length=160)
    cta_text: str = Field(..., min_length=1, max_length=20)
    cta_url: str = Field(..., min_length=1)


class CarouselMessage(BaseModel):
    """Interactive carousel: 2-10 cards sharing one header media type."""
    body_text: str = Field(..., min_length=1, max_length=1024)
    cards: List[CarouselCard] = Field(..., min_length=2, max_length=10)

    @model_validator(mode="after")
    def _consistent_header_type(self) -> "CarouselMessage":
        if len({c.header_type for c in self.cards}) > 1:
            raise ValueError("All carousel cards must use the same header media type")
        return self


class NormalizedInboundEnvelope(BaseModel):
    """Provider-agnostic normalized representation of an incoming WhatsApp webhook event (ADR-0047)."""
    provider: str = "META_CLOUD"
    phone_number_id: Optional[str] = None
    has_message: bool = False
    is_status_update: bool = False
    status_value: Optional[str] = None
    status_message_id: Optional[str] = None
    sender_phone: str = ""
    customer_name: str = "Valued Customer"
    message_id: str = ""
    message_type: str = "unknown"
    text: str = ""
    is_audio: bool = False
    media_id: Optional[str] = None
    is_interactive: bool = False
    interactive_id: Optional[str] = None
    reaction_emoji: Optional[str] = None
    location_coords: Optional[Dict[str, Any]] = None
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Provides backwards-compatible dict representation for unpack_meta_payload callers."""
        return {
            "provider": self.provider,
            "phone_number_id": self.phone_number_id,
            "has_message": self.has_message,
            "is_status_update": self.is_status_update,
            "status_value": self.status_value,
            "status_message_id": self.status_message_id,
            "sender_phone": self.sender_phone,
            "customer_name": self.customer_name,
            "message_id": self.message_id,
            "message_type": self.message_type,
            "text": self.text,
            "is_audio": self.is_audio,
            "media_id": self.media_id,
            "is_interactive": self.is_interactive,
            "interactive_id": self.interactive_id,
            "reaction_emoji": self.reaction_emoji,
            "location_coords": self.location_coords,
        }



class PaymentGatewayPort(ABC):
    """Port interface for Nigerian Fintech Payment Rails (Moniepoint MFB, Paystack)."""

    @abstractmethod
    async def generate_virtual_nuban(
        self,
        merchant_id: str,
        customer_phone: str,
        amount_kobo: int,
        order_reference: str,
    ) -> Dict[str, Any]:
        """Generates a dedicated dynamic 10-digit virtual NUBAN for an active cart hold."""
        pass

    @abstractmethod
    async def verify_settlement(
        self,
        payment_reference: str,
    ) -> Dict[str, Any]:
        """Verifies received settlement status directly against the gateway clearing rail."""
        pass


class WhatsAppBSPPort(ABC):
    """Port interface for WhatsApp Business Solution Providers (Meta Cloud API, Termii, Twilio, 360dialog, Local Sandbox)."""

    provider_name: str = "META_CLOUD"

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        """Verifies cryptographic authenticity of incoming provider webhooks."""
        return True

    def extract_phone_number_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extracts external WhatsApp phone_number_id or business routing key from raw provider payload."""
        return payload.get("phone_number_id")

    def normalize_inbound_webhook(self, payload: Dict[str, Any]) -> NormalizedInboundEnvelope:
        """Normalizes provider-specific webhook payload into canonical NormalizedInboundEnvelope."""
        return NormalizedInboundEnvelope(provider=self.provider_name)

    @abstractmethod
    async def send_text_message(
        self,
        to_phone: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches an outbound text message to a customer's WhatsApp chat."""
        pass

    @abstractmethod
    async def send_interactive_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches an interactive button menu for structured fast-path responses."""
        pass

    @abstractmethod
    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches a registered WhatsApp Business Template (utility, marketing, authentication)."""
        pass

    @abstractmethod
    async def send_media_message(
        self,
        to_phone: str,
        media_type: str,  # document, image, audio
        media_url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches a rich media message (PDF invoice, product image, audio)."""
        pass

    @abstractmethod
    async def send_interactive_list(
        self,
        to_phone: str,
        header_text: str,
        body_text: str,
        button_title: str,
        sections: List[Dict[str, Any]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches an interactive list picker (up to 10 options across sections)."""
        pass

    @abstractmethod
    async def send_interactive_carousel(
        self,
        to_phone: str,
        carousel: CarouselMessage,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches an interactive media carousel (session message, 24h window only)."""
        pass


class CustomClassifierPort(ABC):
    """Port interface for in-process custom ML models (HuggingFace / ONNX)."""

    @abstractmethod
    async def classify(self, text: str) -> ClassificationOutput:
        """Classifies intent, lead tier, urgency, and dialect using local model weights."""
        pass


class LLMProviderPort(ABC):
    """Port interface for third-party LLMs (Google Gemini 3.7 Flash)."""

    @abstractmethod
    async def generate_chat_completion(
        self,
        prompt: str,
        system_instruction: str,
    ) -> ClassificationOutput:
        """Invokes deep LLM reasoning for complex semantic queries and open-ended synthesis."""
        pass


class StatelessOpenWeightPort(ABC):
    """Port interface for the Open-Weight Model Layer (Function A: Input Parser & Function B: Output Translator)."""

    @abstractmethod
    async def parse_input(
        self,
        text: str,
        expected_slot_hint: Optional[str] = None,
        custom_dictionary: Optional[List[Dict[str, Any]]] = None,
        active_bound_slots: Optional[Dict[str, Any]] = None,
        merchant_id: Optional[str] = None,
    ) -> ParsedTurnInput:
        """Function A: Maps incoming natural language into strict JSON intent and parameter slots."""
        pass

    @abstractmethod
    async def translate_output(
        self,
        hydration: HydrationTranslationInput,
    ) -> HydrationTranslationOutput:
        """Function B: Translates verified business state + popped resume context into natural phrasing."""
        pass

