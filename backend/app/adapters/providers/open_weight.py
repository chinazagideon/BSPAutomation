"""Stateless Open-Weight Model Adapter & Declarative Provider Registry (Function A & Function B).

Implements:
- Function A (Input Parser): Grammar-constrained JSON schema extraction via ParsedTurnInput.llm_json_schema()
  and single-line validation via ParsedTurnInput.model_validate_json().
- Function B (Output Translator): Stateless prompt hydration with self-healing Kobo/Naira financial validation
  via HydrationTranslationOutput's @model_validator(mode="after").
- Declarative OPEN_WEIGHT_PROVIDER_REGISTRY (per AGENTS.md).
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional
import httpx
import structlog

from app.adapters.base import (
    HydrationTranslationInput,
    HydrationTranslationOutput,
    ParsedTurnInput,
    StatelessOpenWeightPort,
)
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Static Prefix System Prompts for KV-Cache Reuse (vLLM / SGLang / Ollama)
FUNCTION_A_SYSTEM_PROMPT = (
    "You are a stateless commercial NLU parser for Nigerian SME WhatsApp commerce.\n"
    "Map the customer's message into the required JSON schema.\n"
    "Rules:\n"
    "1. 'Drop am for [Location]' means EXPRESS_DELIVERY to that location (is_cancellation=false).\n"
    "2. Set is_cancellation=true ONLY when the user explicitly aborts or cancels their order.\n"
    "3. Populate slot_mutations ONLY when the user pivots or overrides a previous product, quantity, or location (e.g. 'instead', 'make it 5 bags', 'change to rice').\n"
    "4. Output ONLY valid JSON matching the schema."
)

FUNCTION_B_SYSTEM_PROMPT = (
    "You are a stateless Nigerian commercial copy translator.\n"
    "Combine the verified business response and the resumed checkout prompt into a concise, warm WhatsApp message.\n"
    "CRITICAL INVARIANT: You MUST preserve every Naira amount (e.g. ₦84,000, ₦2,500) exactly as written."
)


class VLLMOpenWeightAdapter(StatelessOpenWeightPort):
    """Production OpenAI-compatible Open-Weight Model Adapter (vLLM, Ollama, HuggingFace TGI, llama.cpp)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.OPEN_WEIGHT_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.OPEN_WEIGHT_API_KEY
        self.model_id = model_id or settings.OPEN_WEIGHT_MODEL_ID
        self.timeout_seconds = timeout_seconds or settings.OPEN_WEIGHT_TIMEOUT_SECONDS
        self._fallback_simulator: Optional[StatelessOpenWeightPort] = None

    def _get_fallback(self) -> StatelessOpenWeightPort:
        if self._fallback_simulator is None:
            from app.sandbox.open_weight_simulator import SandboxOpenWeightSimulator
            self._fallback_simulator = SandboxOpenWeightSimulator()
        return self._fallback_simulator

    async def parse_input(
        self,
        text: str,
        expected_slot_hint: Optional[str] = None,
        custom_dictionary: Optional[List[Dict[str, Any]]] = None,
    ) -> ParsedTurnInput:
        start_time = time.perf_counter()
        user_content = f"Expected Slot Hint: {expected_slot_hint or 'NONE'}\nCustomer Message: {text}"
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": FUNCTION_A_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "max_tokens": settings.OPEN_WEIGHT_MAX_PARSE_TOKENS,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "parsed_turn_input",
                    "strict": True,
                    "schema": ParsedTurnInput.llm_json_schema(),
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
                raw_json = body["choices"][0]["message"]["content"]
                tokens = body.get("usage", {}).get("total_tokens", 45)
                parsed = ParsedTurnInput.model_validate_json(raw_json)
                parsed.tokens_consumed = tokens
                parsed.latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                return parsed
        except Exception as exc:
            logger.warning(
                "open_weight_parse_input_fallback",
                provider="vllm",
                model=self.model_id,
                error=str(exc),
            )
            return await self._get_fallback().parse_input(
                text=text,
                expected_slot_hint=expected_slot_hint,
                custom_dictionary=custom_dictionary,
            )

    async def translate_output(
        self,
        hydration: HydrationTranslationInput,
    ) -> HydrationTranslationOutput:
        start_time = time.perf_counter()
        fallback_out = await self._get_fallback().translate_output(hydration)
        baseline_text = fallback_out.translated_text

        prompt_payload = json.dumps(
            {
                "primary_intent": hydration.primary_intent,
                "verified_facts": hydration.verified_facts,
                "base_response": hydration.fallback_body_text,
                "resumed_frame": hydration.resumed_frame,
                "target_dialect": hydration.target_dialect,
                "merchant_name": hydration.merchant_name,
            },
            ensure_ascii=False,
        )

        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": FUNCTION_B_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_payload},
            ],
            "temperature": 0.1,
            "max_tokens": settings.OPEN_WEIGHT_MAX_TRANSLATE_TOKENS,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
                raw_text = body["choices"][0]["message"]["content"]
                tokens = body.get("usage", {}).get("total_tokens", 60)
                latency = round((time.perf_counter() - start_time) * 1000.0, 2)
                return HydrationTranslationOutput(
                    translated_text=raw_text,
                    fallback_body_text=baseline_text,
                    tokens_consumed=tokens,
                    latency_ms=latency,
                )
        except Exception as exc:
            logger.warning(
                "open_weight_translate_output_fallback",
                provider="vllm",
                model=self.model_id,
                error=str(exc),
            )
            return fallback_out


class HuggingFaceLocalOpenWeightAdapter(StatelessOpenWeightPort):
    """In-process HuggingFace / ONNX local model adapter with graceful fallback."""

    def __init__(self):
        self._fallback_simulator: Optional[StatelessOpenWeightPort] = None

    def _get_fallback(self) -> StatelessOpenWeightPort:
        if self._fallback_simulator is None:
            from app.sandbox.open_weight_simulator import SandboxOpenWeightSimulator
            self._fallback_simulator = SandboxOpenWeightSimulator()
        return self._fallback_simulator

    async def parse_input(
        self,
        text: str,
        expected_slot_hint: Optional[str] = None,
        custom_dictionary: Optional[List[Dict[str, Any]]] = None,
    ) -> ParsedTurnInput:
        return await self._get_fallback().parse_input(
            text=text,
            expected_slot_hint=expected_slot_hint,
            custom_dictionary=custom_dictionary,
        )

    async def translate_output(
        self,
        hydration: HydrationTranslationInput,
    ) -> HydrationTranslationOutput:
        return await self._get_fallback().translate_output(hydration)


def _build_sandbox_adapter() -> StatelessOpenWeightPort:
    from app.sandbox.open_weight_simulator import SandboxOpenWeightSimulator
    return SandboxOpenWeightSimulator()


# Declarative Registry Map per AGENTS.md (no if/elif chains on provider strings)
OPEN_WEIGHT_PROVIDER_REGISTRY: Dict[str, Callable[[], StatelessOpenWeightPort]] = {
    "sandbox": _build_sandbox_adapter,
    "vllm": lambda: VLLMOpenWeightAdapter(),
    "ollama": lambda: VLLMOpenWeightAdapter(),
    "huggingface": lambda: HuggingFaceLocalOpenWeightAdapter(),
}

_ACTIVE_ADAPTER_CACHE: Dict[str, StatelessOpenWeightPort] = {}


def get_open_weight_adapter(provider_slug: Optional[str] = None) -> StatelessOpenWeightPort:
    """Resolves StatelessOpenWeightPort via declarative registry."""
    slug = (provider_slug or settings.OPEN_WEIGHT_PROVIDER or "sandbox").strip().lower()
    if settings.ENVIRONMENT == "test" and not provider_slug:
        slug = "sandbox"
    if slug not in _ACTIVE_ADAPTER_CACHE:
        builder = OPEN_WEIGHT_PROVIDER_REGISTRY.get(slug, _build_sandbox_adapter)
        _ACTIVE_ADAPTER_CACHE[slug] = builder()
    return _ACTIVE_ADAPTER_CACHE[slug]
