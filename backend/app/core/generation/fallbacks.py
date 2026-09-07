"""Deterministic Fallback Factories for Structured Generation (ADR-0039 & ADR-0040)."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, Callable
from pydantic import BaseModel

from app.contexts.desk.schemas import SixFieldContextCard


class FallbackFactory(ABC):
    """Abstract deterministic schema builder for guaranteed type-safe fallback."""

    @abstractmethod
    def build_fallback(self, prompt: str, context: Optional[Any] = None) -> BaseModel:
        pass


class SixFieldContextCardFallbackFactory(FallbackFactory):
    """Deterministic regex & heuristic builder for Desk 6-field context card."""

    def build_fallback(self, prompt: str, context: Optional[Any] = None) -> SixFieldContextCard:
        lower = prompt.lower()
        budget = "₦220,000" if any(w in lower for w in ["220", "carton", "wholesale", "bulk"]) else "₦50,000"
        urgency = "HOT" if any(w in lower for w in ["today", "now", "urgent", "pay", "order", "asap"]) else "WARM"
        dialect = "Nigerian Pidgin" if any(w in lower for w in ["abeg", "dey", "wetin", "how far", "oya", "fit"]) else "Standard English"

        return SixFieldContextCard(
            executive_summary="Customer is inquiring about product availability and fulfillment dispatch.",
            detected_budget_naira=budget,
            urgency_tier=urgency,
            dialect=dialect,
            key_blockers="Confirming payment verification and delivery timeline.",
            suggested_first_response="Hello! I have received your request and our support desk is on standby to assist.",
        )


class FallbackFactoryRegistry:
    """Registry associating Pydantic schema types with deterministic fallback factories."""
    _factories: Dict[Type[BaseModel], FallbackFactory] = {
        SixFieldContextCard: SixFieldContextCardFallbackFactory()
    }

    @classmethod
    def register(cls, schema: Type[BaseModel], factory: FallbackFactory) -> None:
        cls._factories[schema] = factory

    @classmethod
    def get(cls, schema: Type[BaseModel]) -> Optional[FallbackFactory]:
        return cls._factories.get(schema)
