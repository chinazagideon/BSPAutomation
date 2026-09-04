"""Context Aggregation Pipeline with Inversion-of-Control Registry and NDPA PII Sanitization."""

import asyncio
import structlog
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.contexts.compliance.services import sanitize_nigerian_pii_detailed, RedactedEntity

logger = structlog.get_logger(__name__)


class ContextSlice(BaseModel):
    """An isolated domain state slice resolved by a registered provider."""
    slice_name: str
    content: str
    structured_data: Dict[str, Any] = Field(default_factory=dict)
    token_estimate: int = 0
    is_cached: bool = False


class AggregatedContext(BaseModel):
    """Normalized context composite passed to generation engines."""
    merchant_id: Optional[UUID] = None
    customer_phone: Optional[str] = None
    slices: Dict[str, ContextSlice] = Field(default_factory=dict)
    ephemeral_pii_tokens: List[RedactedEntity] = Field(default_factory=list)
    total_token_estimate: int = 0

    def get_slice(self, name: str) -> Optional[ContextSlice]:
        return self.slices.get(name)

    def format_system_prompt_sections(self) -> str:
        """Renders slices into structured markdown sections for model context injection."""
        sections: List[str] = []
        for name, s in self.slices.items():
            if s.content.strip():
                header = name.replace("_", " ").title()
                sections.append(f"### {header}:\n{s.content}")
        return "\n\n".join(sections)

    def rehydrate_text(self, text: str) -> str:
        """Safely re-hydrates ephemeral PII tokens in generated model output."""
        hydrated = text
        for entity in self.ephemeral_pii_tokens:
            if entity.token in hydrated:
                hydrated = hydrated.replace(entity.token, entity.value)
        return hydrated


class ContextProvider(ABC):
    """Abstract collector resolving a domain slice under multi-tenant isolation (ADR-0041)."""

    @property
    @abstractmethod
    def slice_name(self) -> str:
        """Unique identifier for this slice (e.g. 'knowledge', 'customer_history', 'desk_state')."""
        pass

    @abstractmethod
    async def resolve(
        self,
        merchant_id: Optional[UUID],
        customer_phone: Optional[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> ContextSlice:
        """Asynchronously fetches the domain slice."""
        pass


class ProviderRegistry:
    """Inversion-of-Control Registry decoupling core generation from domain context modules."""
    _providers: Dict[str, ContextProvider] = {}

    @classmethod
    def register(cls, provider: ContextProvider) -> None:
        cls._providers[provider.slice_name] = provider
        logger.info("context_provider_registered", slice_name=provider.slice_name)

    @classmethod
    def get(cls, slice_name: str) -> Optional[ContextProvider]:
        return cls._providers.get(slice_name)

    @classmethod
    def list_providers(cls) -> List[str]:
        return list(cls._providers.keys())

    @classmethod
    def clear(cls) -> None:
        cls._providers.clear()


class ContextAggregator:
    """Orchestrates concurrent provider resolution with timeout boundaries and NDPA PII masking."""

    def __init__(self, default_timeout_ms: float = 35.0):
        self.default_timeout_ms = default_timeout_ms

    async def aggregate(
        self,
        merchant_id: Optional[UUID],
        customer_phone: Optional[str] = None,
        requested_slices: Optional[List[str]] = None,
        slice_options: Optional[Dict[str, Any]] = None,
        timeout_ms: Optional[float] = None,
    ) -> AggregatedContext:
        timeout = (timeout_ms or self.default_timeout_ms) / 1000.0
        requested = requested_slices or ProviderRegistry.list_providers()
        slice_opts = slice_options or {}

        providers_to_run: List[ContextProvider] = []
        for name in requested:
            p = ProviderRegistry.get(name)
            if p:
                providers_to_run.append(p)
            else:
                logger.warning("requested_slice_provider_missing", slice_name=name)

        async def _run_provider(p: ContextProvider) -> Optional[ContextSlice]:
            try:
                opts = slice_opts.get(p.slice_name, {})
                return await asyncio.wait_for(
                    p.resolve(merchant_id=merchant_id, customer_phone=customer_phone, options=opts),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("context_provider_timeout_exceeded", slice_name=p.slice_name, timeout_ms=timeout * 1000.0)
                return None
            except Exception as e:
                logger.warning("context_provider_error", slice_name=p.slice_name, error=str(e))
                return None

        # Execute providers concurrently
        results = await asyncio.gather(*[_run_provider(p) for p in providers_to_run], return_exceptions=True)
        resolved_slices: Dict[str, ContextSlice] = {}
        all_redacted: List[RedactedEntity] = []
        total_tokens = 0

        for res in results:
            if isinstance(res, ContextSlice):
                # NDPA 2023 Ephemeral PII Tokenization
                sanitized_content, entities = sanitize_nigerian_pii_detailed(res.content)
                res.content = sanitized_content
                all_redacted.extend(entities)
                resolved_slices[res.slice_name] = res
                total_tokens += res.token_estimate

        return AggregatedContext(
            merchant_id=merchant_id,
            customer_phone=customer_phone,
            slices=resolved_slices,
            ephemeral_pii_tokens=all_redacted,
            total_token_estimate=total_tokens,
        )
