"""Google Gemini 3.7 Flash LLM Adapter and Mock Simulator (ADR-0024, ADR-0039, ADR-0044)."""

import time
import json
import structlog
from typing import Dict, Any, Optional
from pydantic import ValidationError

from app.adapters.base import LLMProviderPort, ClassificationOutput
from app.core.config import settings

logger = structlog.get_logger(__name__)

try:
    from google import genai
    from google.genai import types
    GENAI_SDK_AVAILABLE = True
except ImportError:
    GENAI_SDK_AVAILABLE = False
    genai = None  # type: ignore
    types = None  # type: ignore


class GeminiFlashAdapter(LLMProviderPort):
    """Production Google Gemini Flash Adapter with Structured Output (ADR-0044)."""

    def __init__(self, api_key: str, model_name: str = "gemini-3.7-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self._client: Optional[Any] = None
        if GENAI_SDK_AVAILABLE and self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                logger.warning("gemini_client_init_failed", error=str(exc))
                self._client = None

    async def generate_chat_completion(
        self,
        prompt: str,
        system_instruction: str,
    ) -> ClassificationOutput:
        start_time = time.perf_counter()

        # If SDK is missing or client is uninitialized, fallback gracefully
        if not self._client or not GENAI_SDK_AVAILABLE:
            logger.warning(
                "gemini_sdk_or_client_unavailable_fallback_to_desk",
                sdk_available=GENAI_SDK_AVAILABLE,
                has_client=bool(self._client),
            )
            return self._build_handoff_fallback(start_time, "Google GenAI SDK or Client not initialized")

        try:
            # Note: Gemini Developer API mode rejects additionalProperties from arbitrary Dict[str, Any].
            # Using response_mime_type="application/json" with structured schema instruction guarantees valid JSON.
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )

            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Extract token telemetry from usage_metadata (ADR-0044 Q3)
            tokens_consumed = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_consumed = getattr(response.usage_metadata, "total_token_count", 0) or 0

            # Parse and normalize structured JSON output (ADR-0044 Q1 Option B)
            res = self._parse_and_normalize_response(response)
            if not res:
                return self._build_handoff_fallback(start_time, "Empty or unparseable JSON response from Gemini")

            # Finalize telemetry attributes
            if tokens_consumed == 0:
                tokens_consumed = max(50, (len(prompt) + len(str(res.suggested_reply or ""))) // 4)

            res.tokens_consumed = tokens_consumed
            res.latency_ms = round(latency_ms, 2)
            return res

        except Exception as exc:
            # ADR-0044 Q2 & Q7: Catch API errors, quota exhaustion (429), timeouts, invalid models
            logger.warning(
                "gemini_flash_generation_failed_fallback_to_desk",
                error=str(exc),
                model=self.model_name,
            )
            return self._build_handoff_fallback(start_time, str(exc))

    def _parse_and_normalize_response(self, response: Any) -> Optional[ClassificationOutput]:
        """Extracts JSON and normalizes schema constraints for Pydantic type safety."""
        raw_text = getattr(response, "text", "") or ""
        if not raw_text.strip():
            return None

        try:
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                return None

            # 1. Lead Tier
            tier = str(data.get("lead_tier", "WARM")).upper()
            if "HOT" in tier or "1" in tier:
                clean_tier = "HOT"
            elif "COLD" in tier or "3" in tier:
                clean_tier = "COLD"
            else:
                clean_tier = "WARM"

            # 2. Urgency Score (1 to 10)
            urgency_raw = data.get("urgency_score", 7)
            try:
                urgency_num = float(urgency_raw)
                if 0.0 <= urgency_num <= 1.0:
                    urgency_score = int(round(urgency_num * 10))
                else:
                    urgency_score = int(round(urgency_num))
                urgency_score = max(1, min(10, urgency_score))
            except Exception:
                urgency_score = 7

            # 3. Confidence (0.0 to 1.0)
            conf_raw = data.get("confidence", 0.90)
            try:
                conf = float(conf_raw)
                if conf > 1.0 and conf <= 100.0:
                    conf = conf / 100.0
                conf = max(0.0, min(1.0, conf))
            except Exception:
                conf = 0.90

            # 4. Intent & Dialect
            intent = str(data.get("intent", "GENERAL_INQUIRY")).upper().strip()
            dialect = str(data.get("detected_dialect", "Nigerian Commercial Slang")).strip()

            # 5. Suggested Reply & Action
            suggested_reply = data.get("suggested_reply")
            action = data.get("action")

            # 6. Extracted Entities
            extracted_entities = data.get("extracted_entities")
            if not isinstance(extracted_entities, dict):
                extracted_entities = {}

            return ClassificationOutput(
                intent=intent,
                lead_tier=clean_tier,
                urgency_score=urgency_score,
                confidence=conf,
                detected_dialect=dialect,
                suggested_reply=suggested_reply,
                action=action,
                extracted_entities=extracted_entities,
            )
        except Exception as exc:
            logger.warning("gemini_json_parsing_failed", error=str(exc), raw_text=raw_text[:200])
            return None

    def _build_handoff_fallback(self, start_time: float, error_detail: str) -> ClassificationOutput:
        """Constructs an instant agent handoff fallback without billing tokens (ADR-0044)."""
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return ClassificationOutput(
            intent="GENERAL_INQUIRY",
            lead_tier="WARM",
            urgency_score=6,
            confidence=0.50,
            detected_dialect="Nigerian Commercial Slang",
            suggested_reply="Thank you for your message! Our senior customer support desk has received your request and will follow up shortly.",
            action="DISPATCH_AGENT_HANDOFF",
            extracted_entities={"error_fallback": True, "reason": error_detail[:120]},
            tokens_consumed=0,
            latency_ms=round(latency_ms, 2),
        )


class MockLLMAdapter(LLMProviderPort):
    """Local Dev & CI Mock Simulator for Gemini 3.7 Flash LLM."""

    async def generate_chat_completion(
        self,
        prompt: str,
        system_instruction: str,
    ) -> ClassificationOutput:
        start_time = time.perf_counter()
        lower = prompt.lower()

        # Nuanced LLM reasoning simulation
        intent = "COMPLEX_CONSULTATION"
        lead_tier = "WARM"
        urgency_score = 7
        dialect = "Nigerian Pidgin" if "abeg" in lower or "wetin" in lower else "Nigerian Commercial Slang"
        suggested_reply = (
            "No wahala! I understand what you need for your business setup. "
            "Our senior product consultant in Lagos is reviewing your custom requirements right now."
        )

        if "baking" in lower or "bakery" in lower or "flour" in lower:
            suggested_reply = "Welcome! We have industrial bakery ovens and Grade A baking flour ready for dispatch across Ikeja and Ibadan."
            intent = "VERTICAL_SPECIFIC_INQUIRY"
            lead_tier = "HOT"
            urgency_score = 8

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return ClassificationOutput(
            intent=intent,
            lead_tier=lead_tier,
            urgency_score=urgency_score,
            confidence=0.95,
            detected_dialect=dialect,
            suggested_reply=suggested_reply,
            action="NURTURE_OR_ESCALATE_TO_AGENT",
            extracted_entities={"topic": "B2B SME Commercial Inquiry"},
            tokens_consumed=380,
            latency_ms=max(250.0, latency_ms),
        )


def get_llm_provider_adapter() -> LLMProviderPort:
    """Factory creating LLM adapter based on configuration."""
    if not settings.GEMINI_API_KEY or settings.ENVIRONMENT == "test":
        return MockLLMAdapter()
    return GeminiFlashAdapter(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
