"""Sandbox Simulator for the Stateless Open-Weight Model Layer (Function A & Function B).

Isolated inside app/sandbox/ per AGENTS.md.
- Function A (parse_input): Delegates intent, slot, contrastive mutation, and multi-item `line_items` extraction
  to the natively trained `SpacyNLUEngine`.
- Function B (translate_output): Deterministic prompt hydration & translation with Kobo/Naira financial invariants.
"""

import time
from typing import Any, Dict, List, Optional

from app.adapters.base import (
    HydrationTranslationInput,
    HydrationTranslationOutput,
    ParsedTurnInput,
    StatelessOpenWeightPort,
)
from app.adapters.providers.spacy_nlu_engine import get_spacy_nlu_engine


class SandboxOpenWeightSimulator(StatelessOpenWeightPort):
    """Deterministic local simulator for Open-Weight Function A (Input Parser) and Function B (Translator)."""

    async def parse_input(
        self,
        text: str,
        expected_slot_hint: Optional[str] = None,
        custom_dictionary: Optional[List[Dict[str, Any]]] = None,
        active_bound_slots: Optional[Dict[str, Any]] = None,
        merchant_id: Optional[str] = None,
    ) -> ParsedTurnInput:
        engine = get_spacy_nlu_engine()
        return engine.predict_intent_and_slots(
            text=text,
            expected_slot_hint=expected_slot_hint,
            custom_dictionary=custom_dictionary,
            active_bound_slots=active_bound_slots,
            merchant_id=merchant_id,
        )

    async def translate_output(
        self,
        hydration: HydrationTranslationInput,
    ) -> HydrationTranslationOutput:
        start_time = time.perf_counter()
        base_text = (hydration.fallback_body_text or "").strip()
        resumed = hydration.resumed_frame

        if not resumed:
            latency = (time.perf_counter() - start_time) * 1000.0
            return HydrationTranslationOutput(
                translated_text=base_text,
                fallback_body_text=base_text,
                tokens_consumed=0,
                latency_ms=round(max(1.0, latency), 2),
            )

        bound = resumed.get("bound_slots") or {}
        missing = resumed.get("missing_slots") or []
        resume_prompt = resumed.get("clarification_prompt") or ""
        product_label = bound.get("product_name") or bound.get("product") or "your item"
        qty_label = bound.get("quantity")

        is_pidgin = hydration.target_dialect == "Nigerian Pidgin"
        line_items = bound.get("line_items")
        if isinstance(line_items, list) and len(line_items) > 1:
            order_desc = " + ".join(
                f"{item.get('quantity', 1)}x {item.get('product_name') or item.get('product') or 'item'}"
                for item in line_items
            )
        else:
            order_desc = f"{qty_label}x {product_label}" if qty_label else f"{product_label}"

        if not resume_prompt:
            next_slot = missing[0] if missing else "details"
            if next_slot == "delivery_zone":
                resume_prompt = (
                    f"Which area make we deliver your *{order_desc}* to?"
                    if is_pidgin
                    else f"Where should we deliver your *{order_desc}*?"
                )
            elif next_slot == "fulfillment_type":
                resume_prompt = (
                    f"For your *{order_desc}*, you wan Express Delivery or Warehouse Pickup?"
                    if is_pidgin
                    else f"For your *{order_desc}*, would you prefer Express Delivery or Warehouse Pickup?"
                )
            elif next_slot == "quantity":
                resume_prompt = (
                    f"How many bags/units of *{product_label}* you wan reserve?"
                    if is_pidgin
                    else f"How many units of *{product_label}* would you like to reserve?"
                )
            else:
                resume_prompt = (
                    f"Which brand/size of *{product_label}* you wan pick?"
                    if is_pidgin
                    else f"Which option for *{product_label}* would you like to select?"
                )

        bridge_header = (
            f"🔄 *Back to your active order ({order_desc}):*"
            if not is_pidgin
            else f"🔄 *Make we continue your order ({order_desc}):*"
        )
        combined = f"{base_text}\n\n{bridge_header}\n{resume_prompt}"
        latency = (time.perf_counter() - start_time) * 1000.0

        return HydrationTranslationOutput(
            translated_text=combined,
            fallback_body_text=combined,
            tokens_consumed=0,
            latency_ms=round(max(2.0, latency), 2),
        )
