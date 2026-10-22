"""Pydantic Request/Response Schemas for the Local BSP Sandbox (ADR-0047)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SandboxInboundRequest(BaseModel):
    """Request payload from the WebUI Phone Simulator or automated scenario runner."""
    provider: str = "whatsapp"
    phone_number_id: str = "meta_phone_alaba_agro"
    customer_phone: str = "2348031234567"
    customer_name: str = "Tunde Adeleke"
    message_type: str = Field(
        default="text",
        description="text | button_reply | list_reply | audio | reaction | location | status",
    )
    text: str = ""
    interactive_id: Optional[str] = None
    media_id: Optional[str] = None
    reaction_emoji: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    status_value: Optional[str] = None
    status_message_id: Optional[str] = None
    custom_message_id: Optional[str] = None
    execute_worker_inline: bool = True


class SandboxBurstRequest(BaseModel):
    """Dispatches a rapid multi-message burst from a customer to test the 1.2s debounce window."""
    provider: str = "whatsapp"
    phone_number_id: str = "meta_phone_alaba_agro"
    customer_phone: str = "2348031234567"
    customer_name: str = "Tunde Adeleke"
    messages: List[str] = Field(
        default_factory=lambda: [
            "How far boss",
            "I wan order 2 bags of Mama Gold Rice 50kg",
            "make una deliver am to Ikeja",
        ]
    )
    inter_message_delay_ms: int = 120


class SandboxTemplateSendRequest(BaseModel):
    """Dispatches a registered WhatsApp Business Template to re-open an expired 24h Customer Service Window."""
    phone_number_id: str = "meta_phone_alaba_agro"
    to_phone: str = "2348031234567"
    template_name: str = "re_engagement_window_opener"
    language_code: str = "en"
    parameters: List[str] = Field(default_factory=lambda: ["Tunde", "Alaba Agro Depot"])
