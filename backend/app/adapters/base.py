"""Abstract port interfaces for external payment, messaging, ML, and LLM integrations."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class ClassificationOutput(BaseModel):
    """Normalized output contract across all NLU classification engines."""
    intent: str
    lead_tier: str = Field(..., description="HOT, WARM, COLD")
    urgency_score: int = Field(..., ge=1, le=10)
    confidence: float = Field(..., ge=0.0, le=1.0)
    detected_dialect: str = Field(..., description="Nigerian Pidgin, Commercial Slang, Standard English")
    suggested_reply: Optional[str] = None
    action: Optional[str] = None
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    tokens_consumed: int = 0
    latency_ms: float = 0.0


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
    """Port interface for WhatsApp Business Solution Providers (Meta Cloud API, Termii)."""

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
