"""Agnostic Inference Engine & Generation Port Specifications."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Type, TypeVar, Generic
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ExecutionPolicy(str, Enum):
    """Inference execution policies balancing speed, cost, and reasoning depth."""
    FASTEST_PATH = "FASTEST_PATH"          # Stage 1: Deterministic Trigram / Regex only (~1-5ms, 0 tokens)
    LOCAL_MODEL = "LOCAL_MODEL"            # Stage 2: In-process ONNX / HuggingFace local model (~20ms, 0 tokens)
    DEEP_REASONING = "DEEP_REASONING"      # Stage 3: External LLM (Gemini 3.7 Flash) (~380ms, token cost)
    CASCADING_FALLBACK = "CASCADING_FALLBACK"  # 3-stage cascading fallback gated by confidence thresholds


class TaskPriority(str, Enum):
    """Scheduling & billing priority for Three-Tier Soft Limit Degradation (ADR-0040)."""
    CUSTOMER_FACING = "CUSTOMER_FACING"    # Ingress chat, checkout negotiation, booking clarification
    INTERNAL_ADMIN = "INTERNAL_ADMIN"      # Desk 6-field card synthesis, back-office ticket classification


class ClassificationResult(BaseModel):
    """Normalized intent and dialect classification output."""
    intent: str
    lead_tier: str = Field("WARM", description="HOT, WARM, COLD")
    urgency_score: int = Field(5, ge=1, le=10)
    confidence: float = Field(..., ge=0.0, le=1.0)
    detected_dialect: str = Field("Standard English", description="Nigerian Pidgin, Commercial Slang, Standard English")
    suggested_reply: Optional[str] = None
    action: Optional[str] = None
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    routing_source: str = Field("UNKNOWN", description="FAST_PATH, CUSTOM_LOCAL_MODEL, GEMINI_LLM_ESCALATION, FALLBACK_DESK_HANDOFF")
    tokens_consumed: int = 0
    latency_ms: float = 0.0
    estimated_kobo_saved: int = 0


class TextGenerationResult(BaseModel):
    """Free-form text generation response."""
    text: str
    routing_source: str
    tokens_consumed: int = 0
    latency_ms: float = 0.0
    model_name: str = "default"


class InferenceEnginePort(ABC):
    """Agnostic generation interface unifying Trigram, Local Models, and LLMs across all bounded contexts."""

    @abstractmethod
    async def classify(
        self,
        text: str,
        context: Optional[Any] = None,
        policy: ExecutionPolicy = ExecutionPolicy.CASCADING_FALLBACK,
        task_priority: TaskPriority = TaskPriority.CUSTOMER_FACING,
        merchant_id: Optional[Any] = None,
    ) -> ClassificationResult:
        """Executes intent, dialect, and entity classification."""
        pass

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        context: Optional[Any] = None,
        policy: ExecutionPolicy = ExecutionPolicy.DEEP_REASONING,
        task_priority: TaskPriority = TaskPriority.CUSTOMER_FACING,
        merchant_id: Optional[Any] = None,
    ) -> TextGenerationResult:
        """Executes open-ended text synthesis."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        context: Optional[Any] = None,
        policy: ExecutionPolicy = ExecutionPolicy.CASCADING_FALLBACK,
        task_priority: TaskPriority = TaskPriority.INTERNAL_ADMIN,
        merchant_id: Optional[Any] = None,
    ) -> T:
        """Executes structured JSON schema extraction with deterministic fallback support."""
        pass
