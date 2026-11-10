"""Google Gemini 3.7 Flash LLM Adapter and Mock Simulator (ADR-0024, ADR-0039, ADR-0044)."""

import time
import json
import asyncio
import re
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
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="NONE" # Ignores the weather tool entirely
                    )
                )
            )

            max_attempts = 2
            response = None
            for attempt in range(1, max_attempts + 1):
                try:
                    response = await asyncio.wait_for(
                        self._client.aio.models.generate_content(
                            model=self.model_name,
                            contents=prompt,
                            config=config,
                        ),
                        timeout=5.0,
                    )
                    break
                except Exception as exc:
                    err_str = str(exc)
                    is_transient = "503" in err_str or "429" in err_str or isinstance(exc, asyncio.TimeoutError)
                    if attempt < max_attempts and is_transient:
                        logger.warning(
                            "gemini_flash_transient_failure_retrying",
                            attempt=attempt,
                            error=err_str,
                            model=self.model_name,
                        )
                        await asyncio.sleep(0.5)
                        continue
                    raise

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Extract token telemetry from usage_metadata (ADR-0044 Q3)
            tokens_consumed = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_consumed = getattr(response.usage_metadata, "total_token_count", 0) or 0

            # Parse and normalize structured JSON output (ADR-0044 Q1 Option B)
            res = self._parse_and_normalize_response(response)
            if not res:
                return self._build_handoff_fallback(start_time, "Empty or unparseable JSON response from Gemini", prompt)

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
            return self._build_handoff_fallback(start_time, str(exc), prompt)

    def _parse_and_normalize_response(self, response: Any) -> Optional[ClassificationOutput]:
        """Validates and normalizes JSON response declaratively via ClassificationOutput Annotated types."""
        raw_text = (getattr(response, "text", "") or "").strip()
        if not raw_text:
            return None

        try:
            return ClassificationOutput.model_validate_json(raw_text)
        except Exception as exc:
            logger.warning("gemini_json_parsing_failed", error=str(exc), raw_text=raw_text[:200])
            return None

    def _build_handoff_fallback(
        self,
        start_time: float,
        error_detail: str,
        prompt: str = "",
    ) -> ClassificationOutput:
        """Constructs an instant agent handoff fallback or contextual recovery without billing tokens (ADR-0044)."""
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        lower = (prompt or "").lower()

        # Contextual degradation: check if prompt mentions an in-stock commodity
        detected_prod = None
        for p in ["rice", "sugar", "oil", "flour", "beans", "cement", "milk", "garri", "noodles"]:
            if re.search(rf"\b{p}\b", lower):
                detected_prod = p
                break

        if detected_prod:
            logger.info("gemini_fallback_contextual_recovery", detected_product=detected_prod, error=error_detail[:80])
            return ClassificationOutput(
                intent="PRICE_INQUIRY",
                lead_tier="HOT",
                urgency_score=8,
                confidence=0.85,
                detected_dialect="Nigerian Commercial Slang",
                suggested_reply=None,  # ResponseOrchestrator will query catalog for detected_prod
                action="SHOW_PRODUCT_CATALOG",
                extracted_entities={"product": detected_prod, "error_fallback": True, "reason": error_detail[:120]},
                tokens_consumed=0,
                latency_ms=round(latency_ms, 2),
            )

        return ClassificationOutput(
            intent="GENERAL_INQUIRY",
            lead_tier="WARM",
            urgency_score=6,
            confidence=0.50,
            detected_dialect="Nigerian Commercial Slang",
            suggested_reply="Thank you for your message! Our team is processing your inquiry.",
            action="DISPATCH_AGENT_HANDOFF",
            extracted_entities={"error_fallback": True, "reason": error_detail[:120]},
            tokens_consumed=0,
            latency_ms=round(latency_ms, 2),
        )


class MockLLMAdapter(LLMProviderPort):
    """Context-Aware Local Dev, Sandbox & CI Simulator for Gemini 3.7 Flash LLM (ADR-0044, ADR-0047).

    Synthesizes conversational replies grounded in the injected Catalog Manifest,
    Provider Context Manifest, and recent customer turns so multi-turn conversational
    fluency can be tested 100% locally without external API keys.
    """

    async def generate_chat_completion(
        self,
        prompt: str,
        system_instruction: str,
    ) -> ClassificationOutput:
        start_time = time.perf_counter()
        lower = prompt.lower()
        sys_lower = (system_instruction or "").lower()

        # Extract customer message from prompt if formatted with "Customer Message:"
        msg_match = re.search(r"customer\s*message\s*:\s*(.+)", prompt, flags=re.IGNORECASE | re.DOTALL)
        customer_msg = msg_match.group(1).strip() if msg_match else prompt.strip()
        msg_lower = customer_msg.lower()

        # Detect dialect
        is_pidgin = bool(re.search(r"\b(abeg|wetin|no\s*wahala|how\s*far|una|dey|fit|wan|oya|comot|shinkafa|biko)\b", msg_lower))
        dialect = "Nigerian Pidgin" if is_pidgin else "Nigerian Commercial Slang"

        # Extract merchant name from system_instruction if present
        merchant_match = re.search(r"verified\s*merchant\s*:\s*([^\n]+)", system_instruction or "", flags=re.IGNORECASE)
        merchant_name = merchant_match.group(1).strip() if merchant_match else "our store"

        intent = "COMPLEX_CONSULTATION"
        lead_tier = "WARM"
        urgency_score = 7
        action = "NURTURE_OR_ESCALATE_TO_AGENT"
        extracted_entities: Dict[str, Any] = {"topic": "B2B SME Commercial Inquiry"}

        if "baking" in lower or "bakery" in lower or "flour" in lower:
            suggested_reply = "(: Welcome! We have industrial bakery ovens and Grade A baking flour ready for dispatch across Ikeja and Ibadan."
            intent = "VERTICAL_SPECIFIC_INQUIRY"
            lead_tier = "HOT"
            urgency_score = 8
        elif any(w in msg_lower for w in ["rice", "sugar", "oil", "beans", "garri", "cement", "barber", "haircut", "massage", "facial", "inverter", "laptop", "macbook", "starlink", "battery"]):
            # Grounded catalog inquiry
            matched_prod = next(
                (w for w in ["rice", "sugar", "oil", "beans", "garri", "cement", "barber", "haircut", "massage", "facial", "inverter", "laptop", "macbook", "starlink", "battery"] if w in msg_lower),
                "product",
            )
            intent = "PRICE_INQUIRY"
            lead_tier = "HOT"
            urgency_score = 8
            action = "SHOW_PRODUCT_CATALOG"
            extracted_entities = {"product": matched_prod, "topic": "Catalog Grounded Inquiry"}
            if is_pidgin:
                suggested_reply = (
                    f"No wahala! For {merchant_name}, we get beta {matched_prod} for ground right now. "
                    f"Check the options and prices below make you pick the one wey fit your budget!"
                )
            else:
                suggested_reply = (
                    f"Welcome to {merchant_name}! Here are our current verified options and pricing for {matched_prod}:"
                )
        elif any(w in msg_lower for w in ["delivery", "shipping", "dispatch", "how long", "location", "where una dey", "operating hours", "open"]):
            intent = "LOGISTICS_OR_POLICY_INQUIRY"
            lead_tier = "WARM"
            urgency_score = 7
            action = "ANSWER_POLICY_QUERY"
            if is_pidgin:
                suggested_reply = (
                    f"No wahala! {merchant_name} dey open Mon-Sat (8:00 AM - 6:00 PM WAT). "
                    f"We dey run express same-day delivery across Lagos Mainland, Ikeja, Lekki, and Abuja once your Moniepoint transfer clear!"
                )
            else:
                suggested_reply = (
                    f"{merchant_name} operates Mon-Sat (8:00 AM - 6:00 PM WAT) with same-day express dispatch across Lagos Mainland, Ikeja, Lekki, and Abuja upon payment confirmation."
                )
        elif any(w in msg_lower for w in ["agent", "human", "manager", "complain", "issue", "problem", "refund"]):
            intent = "HUMAN_AGENT_HANDOFF"
            lead_tier = "HOT"
            urgency_score = 9
            action = "DISPATCH_AGENT_HANDOFF"
            suggested_reply = (
                "No wahala at all! I don escalate your chat with full context to our live support desk so you no need repeat yourself. An agent go join you now."
                if is_pidgin else
                "I have escalated your conversation with a complete context summary to our live support desk. A specialist will assist you shortly."
            )
        else:
            suggested_reply = (
                "No wahala! I understand what you need for your business setup. "
                "Our senior product consultant in Lagos is reviewing your custom requirements right now."
            )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return ClassificationOutput(
            intent=intent,
            lead_tier=lead_tier,
            urgency_score=urgency_score,
            confidence=0.95,
            detected_dialect=dialect,
            suggested_reply=suggested_reply,
            action=action,
            extracted_entities=extracted_entities,
            tokens_consumed=380,
            latency_ms=max(250.0, latency_ms),
        )



def get_llm_provider_adapter() -> LLMProviderPort:
    """Factory creating LLM adapter based on configuration."""
    if not settings.GEMINI_API_KEY or settings.ENVIRONMENT == "test":
        return MockLLMAdapter()
    return GeminiFlashAdapter(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
