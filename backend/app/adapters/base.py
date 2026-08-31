"""Abstract port interfaces for external payment, messaging, ML, and LLM integrations."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


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
