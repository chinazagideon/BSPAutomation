"""3-Stage Cascading Hybrid NLU Pipeline Orchestrator with Confidence Gates and State Controllers."""

import time
from typing import List, Optional
from app.core.config import settings
from app.contexts.ingress.fast_path import fast_path_classify, extract_commercial_entities
from app.contexts.ingress.templates import synthesize_custom_model_reply
from app.contexts.ingress.schemas import NLUClassificationResponse
from app.adapters.custom_classifier import get_custom_classifier_adapter
from app.adapters.llm import get_llm_provider_adapter


class CascadingNLUPipeline:
    """
    Executes the 3-Stage Cascading Hybrid NLU Pipeline:
    Stage 1: Trigram / Regex Fast-Path (0 tokens, ~2ms)
    Stage 2: Custom Local Model (HuggingFace / ONNX) (0 tokens, ~20ms)
    Stage 3: Google Gemini 3.7 Flash Escalation (400 tokens, ~380ms)
    """

    @staticmethod
    async def process(
        text: str,
        customer_phone: str = "+2348031234567",
        customer_name: str = "Tunde Adeleke",
        previous_context: Optional[List[str]] = None,
        merchant_name: str = "Enterprise SME Store",
    ) -> NLUClassificationResponse:
        pipeline_start = time.perf_counter()
        previous_context = previous_context or []

        # =========================================================================
        # STAGE 1: Fast-Path Deterministic Matcher
        # =========================================================================
        if settings.USE_FAST_PATH:
            fast_path_result = fast_path_classify(text)
            if fast_path_result and fast_path_result.confidence >= settings.FAST_PATH_CONFIDENCE_THRESHOLD:
                total_latency = (time.perf_counter() - pipeline_start) * 1000.0
                return NLUClassificationResponse(
                    routing_source="FAST_PATH",
                    intent=fast_path_result.intent,
                    lead_tier=fast_path_result.lead_tier,
                    urgency_score=fast_path_result.urgency_score,
                    confidence=fast_path_result.confidence,
                    detected_dialect=fast_path_result.detected_dialect,
                    suggested_reply=fast_path_result.suggested_reply,
                    action=fast_path_result.action,
                    extracted_entities=fast_path_result.extracted_entities,
                    latency_ms=round(total_latency, 2),
                    tokens_consumed=0,
                    estimated_kobo_saved=52000,  # ₦520.00 saved vs LLM
                )

        # =========================================================================
        # STAGE 2: Custom Local Classifier (HuggingFace / ONNX)
        # =========================================================================
        if settings.USE_CUSTOM_MODEL:
            custom_adapter = get_custom_classifier_adapter()
            custom_result = await custom_adapter.classify(text)

            # Supplement with deterministic entity extraction
            extracted_entities = extract_commercial_entities(text)
            if custom_result.extracted_entities:
                extracted_entities.update(custom_result.extracted_entities)

            # Confidence Escalation Gate
            if custom_result.confidence >= settings.CUSTOM_MODEL_CONFIDENCE_THRESHOLD:
                # Synthesize localized reply from template bank
                reply = custom_result.suggested_reply or synthesize_custom_model_reply(
                    intent=custom_result.intent,
                    dialect=custom_result.detected_dialect,
                    entities=extracted_entities,
                    merchant_name=merchant_name,
                )
                total_latency = (time.perf_counter() - pipeline_start) * 1000.0
                return NLUClassificationResponse(
                    routing_source="CUSTOM_LOCAL_MODEL",
                    intent=custom_result.intent,
                    lead_tier=custom_result.lead_tier,
                    urgency_score=custom_result.urgency_score,
                    confidence=custom_result.confidence,
                    detected_dialect=custom_result.detected_dialect,
                    suggested_reply=reply,
                    action=custom_result.action or "EXECUTE_LOCAL_INTENT_WORKFLOW",
                    extracted_entities=extracted_entities,
                    latency_ms=round(total_latency, 2),
                    tokens_consumed=0,
                    estimated_kobo_saved=52000,  # ₦520.00 saved vs LLM
                )

        # =========================================================================
        # STAGE 3: Third-Party LLM Escalation (Google Gemini 3.7 Flash)
        # =========================================================================
        if settings.USE_LLM_ESCALATION:
            llm_adapter = get_llm_provider_adapter()
            prompt = (
                f"Customer Name: {customer_name}\n"
                f"Customer Phone: {customer_phone}\n"
                f"Message: {text}\n"
                f"Previous Context: {previous_context[-3:] if previous_context else []}"
            )
            system_instruction = (
                "You are an enterprise conversational AI for a Nigerian SME. "
                "Classify intent, lead tier, urgency, and generate a tone-matched Nigerian Pidgin or English reply."
            )
            llm_result = await llm_adapter.generate_chat_completion(prompt, system_instruction)
            total_latency = (time.perf_counter() - pipeline_start) * 1000.0

            return NLUClassificationResponse(
                routing_source="GEMINI_LLM_ESCALATION",
                intent=llm_result.intent,
                lead_tier=llm_result.lead_tier,
                urgency_score=llm_result.urgency_score,
                confidence=llm_result.confidence,
                detected_dialect=llm_result.detected_dialect,
                suggested_reply=llm_result.suggested_reply,
                action=llm_result.action or "NURTURE_OR_DEEP_RAG",
                extracted_entities=llm_result.extracted_entities or extract_commercial_entities(text),
                latency_ms=round(total_latency, 2),
                tokens_consumed=llm_result.tokens_consumed or 380,
                estimated_kobo_saved=0,
            )

        # =========================================================================
        # GRACEFUL FALLBACK: Human Desk Handoff
        # =========================================================================
        total_latency = (time.perf_counter() - pipeline_start) * 1000.0
        return NLUClassificationResponse(
            routing_source="FALLBACK_DESK_HANDOFF",
            intent="UNRESOLVED_GENERAL_QUERY",
            lead_tier="WARM",
            urgency_score=6,
            confidence=0.50,
            detected_dialect="Nigerian Commercial Slang",
            suggested_reply=f"Thank you for contacting {merchant_name}! Our desk team has received your message and will attend to you shortly.",
            action="DISPATCH_AGENT_HANDOFF",
            extracted_entities=extract_commercial_entities(text),
            latency_ms=round(total_latency, 2),
            tokens_consumed=0,
            estimated_kobo_saved=0,
        )
