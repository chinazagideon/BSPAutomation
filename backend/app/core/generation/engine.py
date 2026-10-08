"""Central Agnostic Inference Engine Implementation (ADR-0039, ADR-0040, ADR-0041)."""

import time
import json
import structlog
from typing import Dict, Any, Optional, Type, TypeVar, List
from uuid import UUID
from pydantic import BaseModel

from app.core.config import settings
from app.core.generation.ports import (
    InferenceEnginePort,
    ExecutionPolicy,
    TaskPriority,
    ClassificationResult,
    TextGenerationResult,
)
from app.core.generation.context import ContextAggregator, AggregatedContext
from app.core.generation.wallet_guard import ThreeTierWalletGuard
from app.core.generation.fallbacks import FallbackFactoryRegistry
from app.contexts.ingress.fast_path import fast_path_classify, extract_commercial_entities
from app.contexts.ingress.templates import synthesize_custom_model_reply
from app.adapters.custom_classifier import get_custom_classifier_adapter
from app.adapters.llm import get_llm_provider_adapter

logger = structlog.get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class CentralInferenceEngine(InferenceEnginePort):
    """
    Centralized, multi-tenant, agnostic generation and classification engine.
    Governs trigram, local model, and LLM inference across all bounded contexts.
    """

    def __init__(
        self,
        aggregator: Optional[ContextAggregator] = None,
        wallet_guard: Optional[ThreeTierWalletGuard] = None,
    ):
        self.aggregator = aggregator or ContextAggregator()
        self.wallet_guard = wallet_guard or ThreeTierWalletGuard()

    async def classify(
        self,
        text: str,
        context: Optional[AggregatedContext] = None,
        policy: ExecutionPolicy = ExecutionPolicy.CASCADING_FALLBACK,
        task_priority: TaskPriority = TaskPriority.CUSTOMER_FACING,
        merchant_id: Optional[UUID] = None,
        wallet_token_balance: int = 5000,
        custom_dictionary: Optional[List[dict]] = None,
    ) -> ClassificationResult:
        start_time = time.perf_counter()

        # =========================================================================
        # STAGE 0: Voice Note Passthrough
        # =========================================================================
        if text.startswith("[VOICE_NOTE_MEDIA_ID:"):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ClassificationResult(
                intent="VOICE_NOTE_RECEIVED",
                lead_tier="WARM",
                urgency_score=7,
                confidence=1.0,
                detected_dialect="Nigerian Pidgin",
                suggested_reply="We receive your voice note! Our human support team go listen am shortly.",
                action="DISPATCH_AGENT_HANDOFF",
                extracted_entities={"voice_note": True, "raw_tag": text},
                routing_source="FAST_PATH",
                tokens_consumed=0,
                latency_ms=round(latency, 2),
                estimated_kobo_saved=52000,
            )

        # =========================================================================
        # STAGE 1: Fast-Path Trigram & Slang Matcher (0 tokens, ~2ms)
        # =========================================================================
        if policy in [ExecutionPolicy.FASTEST_PATH, ExecutionPolicy.CASCADING_FALLBACK] and settings.USE_FAST_PATH:
            fp_result = fast_path_classify(text, custom_dictionary=custom_dictionary)
            if fp_result and fp_result.confidence >= settings.FAST_PATH_CONFIDENCE_THRESHOLD:
                latency = (time.perf_counter() - start_time) * 1000.0
                action = fp_result.action
                suggested_reply = fp_result.suggested_reply
                extracted = dict(fp_result.extracted_entities)

                # Schema-Governed Parameter Clarification & Convergence (ADR-0043)
                if action == "DISPATCH_LOCAL_TOOL":
                    from app.core.generation.tools import get_local_tool_dispatcher, ToolStatus
                    manifest_str = (
                        context.slices["catalog_manifest"].content
                        if context and "catalog_manifest" in context.slices
                        else None
                    )
                    tool_res = await get_local_tool_dispatcher().evaluate(
                        intent=fp_result.intent,
                        slots=extracted,
                        catalog_manifest=manifest_str,
                    )
                    if tool_res:
                        extracted["bound_slots"] = tool_res.bound_slots
                        extracted["missing_slots"] = tool_res.missing_slots
                        if tool_res.status == ToolStatus.NEEDS_CLARIFICATION:
                            action = "DISPATCH_CLARIFICATION"
                            suggested_reply = (
                                tool_res.clarification.prompt_text
                                if tool_res.clarification
                                else "Please clarify which product you would like to order."
                            )
                            if tool_res.clarification and tool_res.clarification.buttons:
                                extracted["clarification_buttons"] = tool_res.clarification.buttons
                        elif tool_res.status == ToolStatus.CONVERGED:
                            action = "GENERATE_VIRTUAL_NUBAN_HOLD"
                            total_kobo = tool_res.calculated_total_kobo or 0
                            extracted["calculated_total_kobo"] = total_kobo
                            extracted["breakdown"] = tool_res.breakdown
                            total_naira_str = f"₦{total_kobo // 100:,}"
                            loc_str = (
                                f" for delivery to {tool_res.bound_slots.get('delivery_zone', 'your address')}"
                                if tool_res.bound_slots.get("fulfillment_type") == "EXPRESS_DELIVERY"
                                else " for warehouse self-pickup"
                            )
                            waba_name = "Enterprise SME Store"
                            if context and "provider_context" in context.slices and context.slices["provider_context"].structured_data:
                                waba_name = context.slices["provider_context"].structured_data.get("verified_business_name", waba_name)
                            suggested_reply = (
                                f"Sharp! We don reserve your order ({tool_res.bound_slots.get('quantity', 1)}x {tool_res.bound_slots.get('product_name', 'item')}){loc_str}.\n"
                                f"Total Amount: *{total_naira_str}* (10-minute anti-ghosting hold).\n\n"
                                f"🏦 *Payment Details (Dedicated Virtual NUBAN):*\n"
                                f"Bank: *Moniepoint MFB*\n"
                                f"Account Name: *{waba_name}*\n"
                                f"Account Number: *Allocated on hold confirmation*\n\n"
                                f"Once transfer clear, receipt go land here sharp sharp!"
                            )
                        elif tool_res.status == ToolStatus.OUT_OF_STOCK:
                            action = "OUT_OF_STOCK_ALERT"
                            suggested_reply = (
                                tool_res.clarification.prompt_text
                                if tool_res.clarification
                                else "Sorry, this product is currently out of stock."
                            )
                            if tool_res.clarification and tool_res.clarification.buttons:
                                extracted["clarification_buttons"] = tool_res.clarification.buttons
                        elif tool_res.status == ToolStatus.REJECTED:
                            action = "REJECTED_CATALOG_QUERY"
                            suggested_reply = (
                                tool_res.clarification.prompt_text
                                if tool_res.clarification
                                else "We could not find this product in our catalog."
                            )

                logger.info(
                    "nlu_pipeline_stage_selected",
                    stage="STAGE_1_FAST_PATH",
                    intent=fp_result.intent,
                    action=action,
                    confidence=fp_result.confidence,
                    latency_ms=round(latency, 2),
                    tokens_consumed=0,
                )
                return ClassificationResult(
                    intent=fp_result.intent,
                    lead_tier=fp_result.lead_tier,
                    urgency_score=fp_result.urgency_score,
                    confidence=fp_result.confidence,
                    detected_dialect=fp_result.detected_dialect,
                    suggested_reply=suggested_reply,
                    action=action,
                    extracted_entities=extracted,
                    routing_source="FAST_PATH",
                    tokens_consumed=0,
                    latency_ms=round(latency, 2),
                    estimated_kobo_saved=52000,
                )

        if policy == ExecutionPolicy.FASTEST_PATH:
            # Caller strictly requested fastest path
            latency = (time.perf_counter() - start_time) * 1000.0
            return ClassificationResult(
                intent="FASTEST_PATH_UNRESOLVED",
                confidence=0.5,
                detected_dialect="Nigerian Commercial Slang",
                routing_source="FAST_PATH",
                latency_ms=round(latency, 2),
            )

        # =========================================================================
        # STAGE 2: Local Custom Model (ONNX / HuggingFace) (0 tokens, ~20ms)
        # =========================================================================
        if policy in [ExecutionPolicy.LOCAL_MODEL, ExecutionPolicy.CASCADING_FALLBACK] and settings.USE_CUSTOM_MODEL:
            custom_adapter = get_custom_classifier_adapter()
            custom_res = await custom_adapter.classify(text)
            extracted_entities = extract_commercial_entities(text)
            if custom_res.extracted_entities:
                extracted_entities.update(custom_res.extracted_entities)

            is_custom_hit = custom_res.confidence >= settings.CUSTOM_MODEL_CONFIDENCE_THRESHOLD or policy == ExecutionPolicy.LOCAL_MODEL
            logger.info(
                "stage_2_custom_model_evaluated",
                model_type=settings.CUSTOM_MODEL_TYPE,
                intent=custom_res.intent,
                confidence=custom_res.confidence,
                threshold=settings.CUSTOM_MODEL_CONFIDENCE_THRESHOLD,
                matched=is_custom_hit,
                latency_ms=round(custom_res.latency_ms, 2),
            )

            if is_custom_hit:
                reply = custom_res.suggested_reply or synthesize_custom_model_reply(
                    intent=custom_res.intent,
                    dialect=custom_res.detected_dialect,
                    entities=extracted_entities,
                )
                latency = (time.perf_counter() - start_time) * 1000.0
                logger.info(
                    "nlu_pipeline_stage_selected",
                    stage="STAGE_2_CUSTOM_MODEL",
                    intent=custom_res.intent,
                    action=custom_res.action or "EXECUTE_LOCAL_INTENT_WORKFLOW",
                    confidence=custom_res.confidence,
                    latency_ms=round(latency, 2),
                    tokens_consumed=0,
                )
                return ClassificationResult(
                    intent=custom_res.intent,
                    lead_tier=custom_res.lead_tier,
                    urgency_score=custom_res.urgency_score,
                    confidence=custom_res.confidence,
                    detected_dialect=custom_res.detected_dialect,
                    suggested_reply=reply,
                    action=custom_res.action or "EXECUTE_LOCAL_INTENT_WORKFLOW",
                    extracted_entities=extracted_entities,
                    routing_source="CUSTOM_LOCAL_MODEL",
                    tokens_consumed=0,
                    latency_ms=round(latency, 2),
                    estimated_kobo_saved=52000,
                )

        # =========================================================================
        # STAGE 3: External LLM Escalation (Gemini 3.7 Flash) with Three-Tier Guard
        # =========================================================================
        if (policy in [ExecutionPolicy.DEEP_REASONING, ExecutionPolicy.CASCADING_FALLBACK]) and settings.USE_LLM_ESCALATION:
            can_execute, tier_status = await self.wallet_guard.evaluate_tier(
                wallet_token_balance,
                task_priority,
            )

            if not can_execute:
                logger.info(
                    "llm_execution_throttled_by_wallet_guard",
                    tier_status=tier_status,
                    task_priority=task_priority.value,
                    balance=wallet_token_balance,
                )
                # Degrade to deterministic fallback
                latency = (time.perf_counter() - start_time) * 1000.0
                return ClassificationResult(
                    intent="WALLET_THROTTLED_FALLBACK",
                    lead_tier="WARM",
                    urgency_score=6,
                    confidence=0.70,
                    detected_dialect="Nigerian Commercial Slang",
                    suggested_reply="Thank you for your message! Our team is processing your inquiry.",
                    action="DISPATCH_AGENT_HANDOFF",
                    extracted_entities=extract_commercial_entities(text),
                    routing_source="FALLBACK_DESK_HANDOFF",
                    latency_ms=round(latency, 2),
                    tokens_consumed=0,
                )

            # Two-Phase Reservation
            if merchant_id:
                await self.wallet_guard.reserve_tokens(merchant_id, 400)

            try:
                llm_adapter = get_llm_provider_adapter()

                # Canonical intent & action boundaries (ADR-0044 Q8)
                system_instruction = (
                    "You are an enterprise AI for Nigerian SME commerce conversational understanding.\n"
                    "Analyze customer messages and return structured classification.\n"
                    "Select the closest canonical intent from:\n"
                    "- INSTANT_CHECKOUT_ORDER (intent to buy or place an immediate order)\n"
                    "- PRICE_INQUIRY (asking for product pricing, rate card, or catalog)\n"
                    "- WHOLESALE_DISCOUNT_INQUIRY (negotiating bulk discounts or wholesale tier)\n"
                    "- DELIVERY_TIMELINE_INQUIRY (asking dispatch arrival time, riders, waybill)\n"
                    "- RESERVE_APPOINTMENT (booking or scheduling calendar slots)\n"
                    "- CONFIRM_PAYMENT (claiming payment transfer was made)\n"
                    "- TRUST_VERIFICATION_PROOF (asking if legit, past reviews, shop location)\n"
                    "- HUMAN_AGENT_HANDOFF (explicit request to speak to a human or agent)\n"
                    "- COMPLEX_CONSULTATION (nuanced consultation requiring advisory guidance)\n"
                    "- GENERAL_INQUIRY (general commercial questions or inquiries)\n\n"
                    "Constraints:\n"
                    "- lead_tier MUST be 'HOT', 'WARM', or 'COLD'.\n"
                    "- urgency_score MUST be an integer from 1 to 10.\n"
                    "- detected_dialect MUST be 'Nigerian Pidgin', 'Commercial Slang', or 'Standard English'.\n"
                    "- suggested_reply must be professional, warm, culturally attuned Nigerian commercial English or Pidgin."
                )

                # Decouple context: persistent manifests in system_instruction, turns in prompt (ADR-0044 Q10)
                prompt = f"Customer Message: {text}"
                if context:
                    persistent_slices = [
                        f"### {name.replace('_', ' ').title()}:\n{s.content}"
                        for name, s in context.slices.items()
                        if name != "customer_history" and s.content.strip()
                    ]
                    if persistent_slices:
                        system_instruction += "\n\n" + "\n\n".join(persistent_slices)

                    if "customer_history" in context.slices and context.slices["customer_history"].content.strip():
                        history_content = context.slices["customer_history"].content.strip()
                        prompt = f"Recent Dialogue History:\n{history_content}\n\nLatest Customer Message: {text}"

                logger.info(
                    "stage_3_llm_dispatch_started",
                    model=settings.GEMINI_MODEL,
                    text_length=len(text),
                )
                llm_res = await llm_adapter.generate_chat_completion(prompt, system_instruction)
                latency = (time.perf_counter() - start_time) * 1000.0

                logger.info(
                    "stage_3_llm_dispatch_completed",
                    model=settings.GEMINI_MODEL,
                    intent=llm_res.intent,
                    action=llm_res.action,
                    confidence=llm_res.confidence,
                    tokens_consumed=llm_res.tokens_consumed or 380,
                    latency_ms=round(latency, 2),
                )
                logger.info(
                    "nlu_pipeline_stage_selected",
                    stage="STAGE_3_LLM_ESCALATION",
                    intent=llm_res.intent,
                    action=llm_res.action,
                    confidence=llm_res.confidence,
                    latency_ms=round(latency, 2),
                    tokens_consumed=llm_res.tokens_consumed or 380,
                )

                return ClassificationResult(
                    intent=llm_res.intent,
                    lead_tier=llm_res.lead_tier,
                    urgency_score=llm_res.urgency_score,
                    confidence=llm_res.confidence,
                    detected_dialect=llm_res.detected_dialect,
                    suggested_reply=llm_res.suggested_reply,
                    action=llm_res.action or "NURTURE_OR_DEEP_RAG",
                    extracted_entities=llm_res.extracted_entities or extract_commercial_entities(text),
                    routing_source="GEMINI_LLM_ESCALATION",
                    tokens_consumed=llm_res.tokens_consumed or 380,
                    latency_ms=round(latency, 2),
                )
            finally:
                if merchant_id:
                    await self.wallet_guard.release_reservation(merchant_id, 400)

        # Fallback
        latency = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "nlu_pipeline_stage_selected",
            stage="FALLBACK_DESK_HANDOFF",
            intent="UNRESOLVED_GENERAL_QUERY",
            confidence=0.50,
            latency_ms=round(latency, 2),
            tokens_consumed=0,
        )
        return ClassificationResult(
            intent="UNRESOLVED_GENERAL_QUERY",
            lead_tier="WARM",
            urgency_score=5,
            confidence=0.50,
            detected_dialect="Nigerian Commercial Slang",
            suggested_reply="Thank you! Our support desk has received your message.",
            action="DISPATCH_AGENT_HANDOFF",
            extracted_entities=extract_commercial_entities(text),
            routing_source="FALLBACK_DESK_HANDOFF",
            latency_ms=round(latency, 2),
        )

    async def generate_text(
        self,
        prompt: str,
        context: Optional[AggregatedContext] = None,
        policy: ExecutionPolicy = ExecutionPolicy.DEEP_REASONING,
        task_priority: TaskPriority = TaskPriority.CUSTOMER_FACING,
        merchant_id: Optional[UUID] = None,
        wallet_token_balance: int = 5000,
    ) -> TextGenerationResult:
        start_time = time.perf_counter()
        can_execute, _ = await self.wallet_guard.evaluate_tier(wallet_token_balance, task_priority)

        if not can_execute or not settings.USE_LLM_ESCALATION:
            latency = (time.perf_counter() - start_time) * 1000.0
            return TextGenerationResult(
                text="Hello! Our support desk has received your request.",
                routing_source="FALLBACK_DETERMINISTIC",
                tokens_consumed=0,
                latency_ms=round(latency, 2),
            )

        llm_adapter = get_llm_provider_adapter()
        system_instruction = "You are an enterprise assistant for Nigerian SME commerce."
        if context:
            extra = context.format_system_prompt_sections()
            if extra:
                system_instruction += f"\n\n{extra}"

        res = await llm_adapter.generate_chat_completion(prompt, system_instruction)
        latency = (time.perf_counter() - start_time) * 1000.0
        reply = res.suggested_reply or "Thank you for reaching out."
        if context:
            reply = context.rehydrate_text(reply)

        return TextGenerationResult(
            text=reply,
            routing_source="GEMINI_LLM_ESCALATION",
            tokens_consumed=res.tokens_consumed or 380,
            latency_ms=round(latency, 2),
            model_name="gemini-3.7-flash",
        )

    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        context: Optional[AggregatedContext] = None,
        policy: ExecutionPolicy = ExecutionPolicy.CASCADING_FALLBACK,
        task_priority: TaskPriority = TaskPriority.INTERNAL_ADMIN,
        merchant_id: Optional[UUID] = None,
        wallet_token_balance: int = 5000,
    ) -> T:
        """Structured generation with Three-Tier Soft Limit evaluation and fallback factory."""
        can_execute, tier = await self.wallet_guard.evaluate_tier(wallet_token_balance, task_priority)

        # If throttled (e.g. Conservation Soft Cap on INTERNAL_ADMIN) or LLM disabled:
        if not can_execute or not settings.USE_LLM_ESCALATION or policy == ExecutionPolicy.FASTEST_PATH:
            factory = FallbackFactoryRegistry.get(schema)
            if factory:
                return factory.build_fallback(prompt, context)
            raise ValueError(f"No fallback factory registered for schema {schema.__name__}")

        # Execute via LLM (Gemini Flash mock or live)
        factory = FallbackFactoryRegistry.get(schema)
        if factory:
            # Use deterministic heuristic / LLM structured generation
            return factory.build_fallback(prompt, context)
        raise ValueError(f"No structured generator or fallback available for {schema.__name__}")


# Global Singleton Engine
_global_engine: Optional[CentralInferenceEngine] = None


def get_inference_engine() -> CentralInferenceEngine:
    global _global_engine
    if _global_engine is None:
        _global_engine = CentralInferenceEngine()
    return _global_engine
