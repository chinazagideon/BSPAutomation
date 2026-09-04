"""3-Stage Cascading Hybrid NLU Pipeline Domain Facade (ADR-0024, ADR-0039, ADR-0040)."""

import time
from typing import List, Optional, Dict, Any
from app.core.config import settings
from app.contexts.ingress.schemas import NLUClassificationResponse
from app.core.generation import (
    get_inference_engine,
    ExecutionPolicy,
    TaskPriority,
    ContextSlice,
    AggregatedContext,
)


class CascadingNLUPipeline:
    """
    Ingress Domain Facade over CentralInferenceEngine.
    Delegates multi-stage classification to the shared generation kernel while preserving
    ingress-specific schema response contracts and lead scoring semantics.
    """

    @staticmethod
    async def process(
        text: str,
        customer_phone: str = "+2348031234567",
        customer_name: str = "Tunde Adeleke",
        previous_context: Optional[List[str]] = None,
        merchant_name: str = "Enterprise SME Store",
        custom_dictionary: Optional[List[dict]] = None,
        catalog_manifest: Optional[str] = None,
        provider_context: Optional[dict] = None,
    ) -> NLUClassificationResponse:
        engine = get_inference_engine()

        # Build context composite for inference engine
        slices: Dict[str, ContextSlice] = {}
        if catalog_manifest:
            slices["catalog_manifest"] = ContextSlice(
                slice_name="catalog_manifest",
                content=catalog_manifest,
                token_estimate=len(catalog_manifest.split()) * 2,
            )
        if provider_context:
            waba_name = provider_context.get("verified_business_name", merchant_name)
            hours = provider_context.get("operating_hours", "Mon-Sat: 8:00 AM - 6:00 PM WAT")
            coverage = provider_context.get("delivery_coverage", "Lagos Mainland, Lekki, Ikeja, Abuja")
            catalog_id = provider_context.get("meta_catalog_id", "N/A")
            content = (
                f"Verified Merchant: {waba_name}\n"
                f"Operating Hours: {hours}\n"
                f"Delivery Coverage: {coverage}\n"
                f"Linked Meta Catalog: {catalog_id}"
            )
            slices["provider_context"] = ContextSlice(
                slice_name="provider_context",
                content=content,
                structured_data=provider_context,
                token_estimate=50,
            )
        if previous_context:
            slices["customer_history"] = ContextSlice(
                slice_name="customer_history",
                content=f"Customer Name: {customer_name}\nCustomer Phone: {customer_phone}\nRecent Turns:\n" + "\n".join(f"- {m}" for m in previous_context[-5:]),
                token_estimate=len(previous_context) * 10,
            )

        context = AggregatedContext(
            customer_phone=customer_phone,
            slices=slices,
        )

        # Delegate to CentralInferenceEngine
        result = await engine.classify(
            text=text,
            context=context,
            policy=ExecutionPolicy.CASCADING_FALLBACK,
            task_priority=TaskPriority.CUSTOMER_FACING,
            custom_dictionary=custom_dictionary,
        )

        return NLUClassificationResponse(
            routing_source=result.routing_source,
            intent=result.intent,
            lead_tier=result.lead_tier,
            urgency_score=result.urgency_score,
            confidence=result.confidence,
            detected_dialect=result.detected_dialect,
            suggested_reply=result.suggested_reply or f"Thank you for contacting {merchant_name}!",
            action=result.action,
            extracted_entities=result.extracted_entities,
            latency_ms=result.latency_ms,
            tokens_consumed=result.tokens_consumed,
            estimated_kobo_saved=result.estimated_kobo_saved,
        )
