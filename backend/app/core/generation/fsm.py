"""Deterministic Finite State Machine (FSM) & LIFO Context Switch Orchestrator.

Decouples conversational dialogue state management from stateless LLM parsing (Function A)
and stateless output translation (Function B):
- Dispatches interactive protocol events via InteractiveProtocolEnvelope Discriminated Union + match/case.
- Manages LIFO ContextStack push, pop, and per-node TTL eviction via ContextStack & NegotiationFrameManager.
- Executes Function B (Dynamic Prompt Hydration) with self-healing Kobo/Naira financial invariants.
"""

from enum import Enum
import time
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.adapters.base import (
    CommandTapAction,
    HydrationTranslationInput,
    InteractiveProtocolEnvelope,
    NavAction,
    OrderSelectAction,
    ParsedTurnInput,
    ProductTapAction,
    SlotBindAction,
)
from app.adapters.providers.open_weight import get_open_weight_adapter
from app.contexts.ingress.pipeline import CascadingNLUPipeline
from app.contexts.ingress.schemas import DialogueTurn
from app.contexts.ingress.templates import synthesize_custom_model_reply
from app.contexts.knowledge.services import KnowledgeService
from app.core.generation.negotiation import (
    ContextStack,
    NegotiationFrame,
    NegotiationFrameManager,
)
from app.core.generation.response_classifier import ResponseStrategy
from app.core.generation.order_ledger import CustomerOrderLedger
from app.core.generation.response_formatter import (
    EgressMessageType,
    EgressPayloadEnvelope,
    ResponseFormatter,
)
from app.core.generation.response_orchestrator import ResponseOrchestrator
from app.core.generation.tools import ToolStatus, get_local_tool_dispatcher

logger = structlog.get_logger(__name__)

# Intents answerable only from merchant knowledge (never from fast-path or hardcoded templates).
KNOWLEDGE_BOUND_INTENTS = frozenset({"DELIVERY_TIMELINE_INQUIRY", "ORDER_STATUS_INQUIRY", "TRUST_VERIFICATION_PROOF"})


class FSMTransitionType(str, Enum):
    """Deterministic state transition classifications."""
    PROTOCOL_DIRECT = "PROTOCOL_DIRECT"
    ADVANCE_FRAME = "ADVANCE_FRAME"
    MUTATE_SLOTS = "MUTATE_SLOTS"
    PUSH_SUBFLOW_AND_POP_RESUME = "PUSH_SUBFLOW_AND_POP_RESUME"
    CANCEL_FLOW = "CANCEL_FLOW"
    AFFIRM_OFFER = "AFFIRM_OFFER"
    NEGATE_OFFER = "NEGATE_OFFER"
    NEW_FLOW = "NEW_FLOW"
    INDEPENDENT_INQUIRY = "INDEPENDENT_INQUIRY"


class FSMTurnOutcome(BaseModel):
    """Normalized turn execution outcome produced by ConversationFSMService."""
    transition: FSMTransitionType
    envelope: EgressPayloadEnvelope
    intent: str
    action: str
    lead_tier: str = "WARM"
    urgency_score: int = 7
    confidence: float = 0.95
    detected_dialect: str = "Standard English"
    routing_source: str = "FSM_ENGINE"
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    tokens_consumed: int = 0
    latency_ms: float = 0.0
    active_frame: Optional[Dict[str, Any]] = None
    context_stack: List[Dict[str, Any]] = Field(default_factory=list)


class ConversationFSMService:
    """Deterministic Finite State Machine coordinating LIFO ContextStack and Stateless Open-Weight LLM."""

    @classmethod
    async def dispatch_interactive_protocol(
        cls,
        merchant_id: Union[UUID, str],
        interactive_id: str,
        customer_phone: str,
        session: Optional[AsyncSession] = None,
        merchant_name: str = "Enterprise SME Store",
        catalog_manifest: Optional[str] = None,
    ) -> EgressPayloadEnvelope:
        """Dispatches WhatsApp interactive callbacks using Discriminated Union + Python match/case (Pattern 5)."""
        m_id = str(merchant_id)
        if merchant_name == "Enterprise SME Store":
            try:
                from app.contexts.ingress.services import IngressService
                provider_ctx = IngressService.get_cached_provider_context(m_id)
                if isinstance(provider_ctx, dict) and provider_ctx.get("verified_business_name"):
                    merchant_name = provider_ctx["verified_business_name"]
            except Exception:
                pass

        protocol_envelope = InteractiveProtocolEnvelope.model_validate(interactive_id or "")
        stack = await NegotiationFrameManager.load_stack(m_id, customer_phone)

        match protocol_envelope.event:
            case ProductTapAction(sku=sku):
                active_frame = stack.peek()
                if not active_frame:
                    active_frame = NegotiationFrame(
                        merchant_id=m_id,
                        active_tool="ProductCatalog",
                        intent="PRICE_INQUIRY",
                        node_type="ATOMIC_QUERY",
                        bound_slots={"sku": sku},
                        missing_slots=[],
                    )
                else:
                    active_frame.intent = "PRICE_INQUIRY"
                    active_frame.bound_slots["sku"] = sku
                stack.push(active_frame)
                await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

                offering = await KnowledgeService.get_offering_by_sku(
                    merchant_id=merchant_id,
                    sku=sku,
                    session=session,
                )
                if offering:
                    return ResponseFormatter.format_product_detail_card(
                        to_phone=customer_phone,
                        offering=offering,
                    )
                return ResponseFormatter.format_catalog_miss(
                    to_phone=customer_phone,
                    query_term=sku,
                    merchant_name=merchant_name,
                )

            case SlotBindAction(slot_name=slot_name, slot_value=slot_val):
                active_frame = stack.peek()
                if not active_frame or active_frame.intent != "INSTANT_CHECKOUT_ORDER":
                    active_frame = NegotiationFrame(
                        merchant_id=m_id,
                        active_tool="CheckoutOrderTool",
                        intent="INSTANT_CHECKOUT_ORDER",
                        node_type="TRANSACTIONAL",
                        bound_slots=(
                            dict(active_frame.bound_slots)
                            if active_frame and slot_name not in ("sku", "offering_id")
                            else {}
                        ),
                        missing_slots=[],
                    )
                elif slot_name in ("sku", "offering_id") and active_frame.bound_slots.get("sku") != slot_val:
                    active_frame.bound_slots = {}

                if slot_name.startswith("line_item_sku:"):
                    try:
                        item_idx = int(slot_name.split(":", 1)[1])
                        line_items = list(active_frame.bound_slots.get("line_items") or [])
                        if 0 <= item_idx < len(line_items):
                            from app.contexts.knowledge.offering_schemas import compute_offering_id
                            updated_item = dict(line_items[item_idx])
                            updated_item["sku"] = slot_val
                            updated_item["offering_id"] = compute_offering_id(m_id, slot_val)
                            line_items[item_idx] = updated_item
                            active_frame.bound_slots["line_items"] = line_items
                    except (ValueError, IndexError):
                        active_frame.bound_slots[slot_name] = slot_val
                else:
                    active_frame.bound_slots[slot_name] = slot_val

                if slot_name in ("sku", "offering_id"):
                    out_of_stock_env = await cls._bind_and_validate_sku(
                        merchant_id=merchant_id,
                        customer_phone=customer_phone,
                        sku_val=slot_val,
                        active_frame=active_frame,
                        session=session,
                        catalog_manifest=catalog_manifest,
                    )
                    if out_of_stock_env is not None:
                        return out_of_stock_env

                if not catalog_manifest:
                    try:
                        from app.contexts.ingress.services import IngressService
                        catalog_manifest = IngressService.get_cached_catalog_manifest(m_id)
                    except Exception:
                        pass

                tool_res = await get_local_tool_dispatcher().evaluate(
                    intent="INSTANT_CHECKOUT_ORDER",
                    slots=active_frame.bound_slots,
                    catalog_manifest=catalog_manifest,
                )
                if tool_res:
                    return await cls._format_tool_evaluation_envelope(
                        merchant_id=m_id,
                        customer_phone=customer_phone,
                        merchant_name=merchant_name,
                        stack=stack,
                        active_frame=active_frame,
                        tool_res=tool_res,
                        session=session,
                    )

            case CommandTapAction(command="SHOW_CATALOG"):
                active_frame = stack.peek() or NegotiationFrame(
                    merchant_id=m_id,
                    active_tool="ProductCatalog",
                    intent="SHOW_PRODUCT_CATALOG",
                    node_type="ATOMIC_QUERY",
                    bound_slots={},
                    missing_slots=[],
                )
                active_frame.intent = "SHOW_PRODUCT_CATALOG"
                stack.push(active_frame)
                await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

                offerings = await KnowledgeService.search_catalog_offerings(
                    merchant_id=merchant_id,
                    query="",
                    session=session,
                )
                return ResponseFormatter.format_interactive_list(
                    to_phone=customer_phone,
                    offerings=offerings,
                    query_title="Catalog",
                )

            case CommandTapAction(command="AGENT_HANDOFF"):
                active_frame = stack.peek() or NegotiationFrame(
                    merchant_id=m_id,
                    active_tool="DeskService",
                    intent="DISPATCH_AGENT_HANDOFF",
                    node_type="HANDOFF",
                    bound_slots={},
                    missing_slots=[],
                )
                active_frame.intent = "DISPATCH_AGENT_HANDOFF"
                active_frame.node_type = "HANDOFF"
                stack.push(active_frame)
                await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

                return ResponseFormatter.format_standard_text(
                    to_phone=customer_phone,
                    text="A human agent will be with you shortly. Please hold on.",
                    strategy=ResponseStrategy.AGENT_HANDOFF,
                )

            case NavAction(target="RESUME_CART"):
                active_frame = stack.peek()
                if active_frame and active_frame.intent == "INSTANT_CHECKOUT_ORDER":
                    tool_res = await get_local_tool_dispatcher().evaluate(
                        intent="INSTANT_CHECKOUT_ORDER",
                        slots=active_frame.bound_slots,
                        catalog_manifest=catalog_manifest,
                    )
                    if tool_res:
                        return await cls._format_tool_evaluation_envelope(
                            merchant_id=m_id,
                            customer_phone=customer_phone,
                            merchant_name=merchant_name,
                            stack=stack,
                            active_frame=active_frame,
                            tool_res=tool_res,
                            session=session,
                        )
                offerings = await KnowledgeService.search_catalog_offerings(
                    merchant_id=merchant_id,
                    query="",
                    session=session,
                )
                return ResponseFormatter.format_interactive_list(
                    to_phone=customer_phone,
                    offerings=offerings,
                    query_title="Catalog",
                )

            case NavAction(target="BROWSE_CATALOG"):
                offerings = await KnowledgeService.search_catalog_offerings(
                    merchant_id=merchant_id,
                    query="",
                    session=session,
                )
                return ResponseFormatter.format_interactive_list(
                    to_phone=customer_phone,
                    offerings=offerings,
                    query_title="Catalog",
                )

            case NavAction(target="TRACK_ORDER"):
                inquiry_res = await CustomerOrderLedger.lookup_order_for_inquiry(
                    merchant_id=m_id,
                    customer_phone=customer_phone,
                    session=session,
                )
                return ResponseFormatter.format_order_status_card(
                    to_phone=customer_phone,
                    order=inquiry_res.order,
                    multiple_orders=inquiry_res.orders if inquiry_res.cardinality == "MULTIPLE" else None,
                    merchant_name=merchant_name,
                )

            case NavAction(target="AGENT_HANDOFF"):
                active_frame = stack.peek() or NegotiationFrame(
                    merchant_id=m_id,
                    active_tool="DeskService",
                    intent="DISPATCH_AGENT_HANDOFF",
                    node_type="HANDOFF",
                    bound_slots={},
                    missing_slots=[],
                )
                active_frame.intent = "DISPATCH_AGENT_HANDOFF"
                active_frame.node_type = "HANDOFF"
                stack.push(active_frame)
                await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)
                return ResponseFormatter.format_standard_text(
                    to_phone=customer_phone,
                    text="A human agent will be with you shortly. Please hold on.",
                    strategy=ResponseStrategy.AGENT_HANDOFF,
                )

            case OrderSelectAction(order_id=order_id):
                inquiry_res = await CustomerOrderLedger.lookup_order_for_inquiry(
                    merchant_id=m_id,
                    customer_phone=customer_phone,
                    order_ref=order_id,
                    session=session,
                )
                return ResponseFormatter.format_order_status_card(
                    to_phone=customer_phone,
                    order=inquiry_res.order,
                    merchant_name=merchant_name,
                )

        return ResponseFormatter.format_interactive_buttons(
            to_phone=customer_phone,
            body_text=f"We couldn't find that item in current stock for {merchant_name}. Please choose an option below:",
            buttons=[
                {"id": "SHOW_CATALOG", "title": "View Catalog"},
                {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
            ],
            strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
        )

    @staticmethod
    async def _run_cascading_nlu(
        merchant_id: Union[UUID, str],
        text: str,
        customer_phone: str,
        customer_name: str,
        recent_history: Optional[Sequence[Union[DialogueTurn, str]]],
        session: Optional[AsyncSession],
        merchant_name: str,
        custom_dictionary: Optional[List[Dict[str, Any]]],
        catalog_manifest: Optional[str],
        provider_context: Optional[Dict[str, Any]],
    ):
        """Invokes CascadingNLUPipeline.process with grounded FAQ and customer order manifests."""
        manifests: Dict[str, Any] = {
            "faq_manifest": None,
            "faq_data": [],
            "customer_orders_manifest": None,
            "customer_orders_data": [],
        }
        if session is not None:
            try:
                from app.contexts.ingress.services import IngressService
                m_uuid = merchant_id if isinstance(merchant_id, UUID) else UUID(str(merchant_id))
                manifests = await IngressService.build_grounding_manifests(
                    session=session,
                    merchant_id=m_uuid,
                    customer_phone=customer_phone,
                )
            except (ValueError, Exception):
                pass

        return await CascadingNLUPipeline.process(
            text=text,
            customer_phone=customer_phone,
            customer_name=customer_name,
            previous_context=recent_history,
            merchant_name=merchant_name,
            custom_dictionary=custom_dictionary,
            catalog_manifest=catalog_manifest,
            provider_context=provider_context,
            faq_manifest=manifests["faq_manifest"],
            customer_orders_manifest=manifests["customer_orders_manifest"],
            faq_data=manifests["faq_data"],
            customer_orders_data=manifests["customer_orders_data"],
        )

    @classmethod
    async def process_turn(
        cls,
        merchant_id: Union[UUID, str],
        customer_phone: str,
        customer_name: str,
        sanitized_text: str,
        recent_history: Optional[Sequence[Union[DialogueTurn, str]]] = None,
        session: Optional[AsyncSession] = None,
        merchant_name: str = "Enterprise SME Store",
        custom_dictionary: Optional[List[Dict[str, Any]]] = None,
        catalog_manifest: Optional[str] = None,
        provider_context: Optional[Dict[str, Any]] = None,
        is_interactive: bool = False,
        interactive_id: Optional[str] = None,
    ) -> FSMTurnOutcome:
        """Executes a single conversational turn through the Deterministic FSM + LIFO ContextStack."""
        start_time = time.perf_counter()
        m_id = str(merchant_id)

        # ---------------------------------------------------------------------
        # 1. 0ms Protocol Fast-Lane for Interactive Button / List Callbacks
        # ---------------------------------------------------------------------
        if is_interactive and interactive_id:
            envelope = await cls.dispatch_interactive_protocol(
                merchant_id=merchant_id,
                interactive_id=interactive_id,
                customer_phone=customer_phone,
                session=session,
                merchant_name=merchant_name,
                catalog_manifest=catalog_manifest,
            )
            stack = await NegotiationFrameManager.load_stack(m_id, customer_phone)
            top = stack.peek()
            action = cls._strategy_to_action(envelope.strategy)
            inbound_intent = cls._resolve_interactive_intent(interactive_id, envelope.strategy, top)
            latency = (time.perf_counter() - start_time) * 1000.0
            return FSMTurnOutcome(
                transition=FSMTransitionType.PROTOCOL_DIRECT,
                envelope=envelope,
                intent=inbound_intent,
                action=action,
                lead_tier="HOT",
                urgency_score=9,
                confidence=1.0,
                detected_dialect="Interactive / Slot-Binding",
                routing_source="NEGOTIATION_FRAME",
                extracted_entities={"interactive_id": interactive_id},
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
                active_frame=top.model_dump(mode="json") if top else None,
                context_stack=[f.model_dump(mode="json") for f in stack.frames],
            )

        # ---------------------------------------------------------------------
        # 2. Load LIFO ContextStack & Invoke Stateless Function A (Input Parser)
        # ---------------------------------------------------------------------
        stack = await NegotiationFrameManager.load_stack(m_id, customer_phone)
        active_frame = stack.peek()
        expected_slot_hint = (
            active_frame.missing_slots[0]
            if active_frame and active_frame.missing_slots
            else None
        )

        open_weight = get_open_weight_adapter()
        parsed: ParsedTurnInput = await open_weight.parse_input(
            text=sanitized_text,
            expected_slot_hint=expected_slot_hint,
            custom_dictionary=custom_dictionary,
            active_bound_slots=active_frame.bound_slots if active_frame else None,
            merchant_id=m_id,
        )

        # ---------------------------------------------------------------------
        # 3. Transition Branch A: Explicit Cancellation (Pops Active LIFO Frame)
        # ---------------------------------------------------------------------
        if parsed.is_cancellation:
            popped = stack.pop()
            parent_frame = stack.peek()
            await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

            cancel_text = "No wahala! We don clear your pending order. Let us know anytime you're ready to order again."
            buttons = None
            strategy = ResponseStrategy.STANDARD_TEXT

            # If a suspended parent transactional frame remains on the stack, offer to resume it
            if parent_frame and parent_frame.missing_slots:
                tool_res = await get_local_tool_dispatcher().evaluate(
                    intent=parent_frame.intent,
                    slots=parent_frame.bound_slots,
                    catalog_manifest=catalog_manifest,
                )
                if tool_res and tool_res.clarification:
                    hydration = await open_weight.translate_output(
                        HydrationTranslationInput(
                            primary_intent="CANCEL_ORDER",
                            fallback_body_text=cancel_text,
                            resumed_frame={
                                "bound_slots": parent_frame.bound_slots,
                                "missing_slots": parent_frame.missing_slots,
                                "clarification_prompt": tool_res.clarification.prompt_text,
                            },
                            target_dialect=parsed.detected_dialect,
                            merchant_name=merchant_name,
                        )
                    )
                    cancel_text = hydration.translated_text
                    buttons = tool_res.clarification.buttons
                    strategy = ResponseStrategy.SLOT_CLARIFICATION

            envelope = (
                ResponseFormatter.format_interactive_buttons(
                    to_phone=customer_phone,
                    body_text=cancel_text,
                    buttons=buttons,
                    strategy=strategy,
                )
                if buttons
                else ResponseFormatter.format_standard_text(
                    to_phone=customer_phone,
                    text=cancel_text,
                    strategy=strategy,
                )
            )
            latency = (time.perf_counter() - start_time) * 1000.0
            return FSMTurnOutcome(
                transition=FSMTransitionType.CANCEL_FLOW,
                envelope=envelope,
                intent="CANCEL_ORDER",
                action="CANCEL_NEGOTIATION_FRAME",
                lead_tier="COLD",
                urgency_score=5,
                confidence=parsed.confidence,
                detected_dialect=parsed.detected_dialect,
                routing_source="NEGOTIATION_FRAME",
                extracted_entities=parsed.slots,
                tokens_consumed=parsed.tokens_consumed,
                latency_ms=round(latency, 2),
                active_frame=parent_frame.model_dump(mode="json") if parent_frame else None,
                context_stack=[f.model_dump(mode="json") for f in stack.frames],
            )

        # ---------------------------------------------------------------------
        # 3b. Independent Knowledge-Bound Inquiry Lane (delivery timeline, trust/location)
        #     Decoupled from the LIFO stack: never pushes, pops, or mutates frames, and is
        #     answerable inside or outside a negotiation, about the current cart or an old order.
        #     Only merchant-KB-grounded answers short-circuit here; ungrounded queries fall
        #     through to Stage 2 / Stage 3 escalation below.
        # ---------------------------------------------------------------------
        if parsed.intent in KNOWLEDGE_BOUND_INTENTS and parsed.confidence >= 0.75:
            inquiry_outcome = await cls._resolve_independent_inquiry(
                merchant_id=m_id,
                customer_phone=customer_phone,
                session=session,
                merchant_name=merchant_name,
                catalog_manifest=catalog_manifest,
                parsed=parsed,
                active_frame=active_frame,
                stack=stack,
                start_time=start_time,
            )
            if inquiry_outcome is not None:
                return inquiry_outcome

        # ---------------------------------------------------------------------
        # 4. Transition Branch B: Active Frame Pending Offer Affirmation / Negation
        # ---------------------------------------------------------------------
        if active_frame and active_frame.pending_offer:
            offer = dict(active_frame.pending_offer)
            if parsed.is_affirmation:
                active_frame.pending_offer = None
                stack.push(active_frame)
                await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

                fake_nlu = {
                    "intent": "PRICE_INQUIRY",
                    "extracted_entities": {
                        "product": offer.get("product") or offer.get("query_term", "")
                    },
                    "suggested_reply": "Here are our current options and prices:",
                }
                envelope = await ResponseOrchestrator.resolve(
                    merchant_id=merchant_id,
                    nlu_result=fake_nlu,
                    customer_phone=customer_phone,
                    raw_message=sanitized_text,
                    session=session,
                    merchant_name=merchant_name,
                )
                latency = (time.perf_counter() - start_time) * 1000.0
                return FSMTurnOutcome(
                    transition=FSMTransitionType.AFFIRM_OFFER,
                    envelope=envelope,
                    intent=active_frame.intent,
                    action="DISPLAY_AFFIRMED_CATALOG_LIST",
                    lead_tier="HOT",
                    urgency_score=9,
                    confidence=1.0,
                    detected_dialect=parsed.detected_dialect,
                    routing_source="NEGOTIATION_FRAME",
                    extracted_entities=parsed.slots,
                    tokens_consumed=parsed.tokens_consumed,
                    latency_ms=round(latency, 2),
                    active_frame=active_frame.model_dump(mode="json"),
                    context_stack=[f.model_dump(mode="json") for f in stack.frames],
                )
            elif parsed.is_negation:
                stack.pop()
                await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)
                reply = "No wahala! We don clear that. Just let us know anytime you need anything."
                envelope = ResponseFormatter.format_standard_text(
                    to_phone=customer_phone,
                    text=reply,
                    strategy=ResponseStrategy.STANDARD_TEXT,
                )
                top = stack.peek()
                latency = (time.perf_counter() - start_time) * 1000.0
                return FSMTurnOutcome(
                    transition=FSMTransitionType.NEGATE_OFFER,
                    envelope=envelope,
                    intent=active_frame.intent,
                    action="CANCEL_PENDING_OFFER",
                    lead_tier="WARM",
                    urgency_score=5,
                    confidence=1.0,
                    detected_dialect=parsed.detected_dialect,
                    routing_source="NEGOTIATION_FRAME",
                    extracted_entities=parsed.slots,
                    tokens_consumed=parsed.tokens_consumed,
                    latency_ms=round(latency, 2),
                    active_frame=top.model_dump(mode="json") if top else None,
                    context_stack=[f.model_dump(mode="json") for f in stack.frames],
                )

        # ---------------------------------------------------------------------
        # 5. Active Transactional Frame Transitions (Mutate vs Advance vs Push Sub-Flow)
        # ---------------------------------------------------------------------
        if active_frame and active_frame.intent == "INSTANT_CHECKOUT_ORDER":
            is_slot_mutation = cls._detect_slot_mutation(active_frame, parsed)
            is_slot_advance = (
                parsed.intent == "INSTANT_CHECKOUT_ORDER"
                or is_slot_mutation
                or cls._provides_relevant_checkout_slot(active_frame, parsed)
            )

            if is_slot_advance:
                transition_type = (
                    FSMTransitionType.MUTATE_SLOTS
                    if is_slot_mutation
                    else FSMTransitionType.ADVANCE_FRAME
                )
                cls._apply_slots_to_frame(active_frame, parsed, is_mutation=is_slot_mutation)

                tool_res = await get_local_tool_dispatcher().evaluate(
                    intent="INSTANT_CHECKOUT_ORDER",
                    slots=active_frame.bound_slots,
                    catalog_manifest=catalog_manifest,
                )
                if tool_res:
                    envelope = await cls._format_tool_evaluation_envelope(
                        merchant_id=m_id,
                        customer_phone=customer_phone,
                        merchant_name=merchant_name,
                        stack=stack,
                        active_frame=active_frame,
                        tool_res=tool_res,
                        session=session,
                    )
                    top = stack.peek()
                    latency = (time.perf_counter() - start_time) * 1000.0
                    return FSMTurnOutcome(
                        transition=transition_type,
                        envelope=envelope,
                        intent="INSTANT_CHECKOUT_ORDER",
                        action=cls._strategy_to_action(envelope.strategy),
                        lead_tier="HOT",
                        urgency_score=9,
                        confidence=parsed.confidence,
                        detected_dialect=parsed.detected_dialect,
                        routing_source="NEGOTIATION_FRAME",
                        extracted_entities=dict(active_frame.bound_slots),
                        tokens_consumed=parsed.tokens_consumed,
                        latency_ms=round(latency, 2),
                        active_frame=top.model_dump(mode="json") if top else None,
                        context_stack=[f.model_dump(mode="json") for f in stack.frames],
                    )

            # Out-of-Context Query during an Active Incomplete Checkout:
            # PUSH sub-flow onto LIFO stack -> EXECUTE sub-flow -> POP sub-flow -> HYDRATE resume via Function B
            if active_frame.missing_slots:
                return await cls._execute_push_subflow_and_pop_resume(
                    merchant_id=merchant_id,
                    customer_phone=customer_phone,
                    customer_name=customer_name,
                    sanitized_text=sanitized_text,
                    recent_history=recent_history,
                    session=session,
                    merchant_name=merchant_name,
                    custom_dictionary=custom_dictionary,
                    catalog_manifest=catalog_manifest,
                    provider_context=provider_context,
                    stack=stack,
                    suspended_frame=active_frame,
                    parsed=parsed,
                    start_time=start_time,
                )

        # ---------------------------------------------------------------------
        # 6. Clean-Slate / New Flow Execution
        # ---------------------------------------------------------------------
        if parsed.intent == "INSTANT_CHECKOUT_ORDER":
            new_frame = NegotiationFrame(
                merchant_id=m_id,
                active_tool="CheckoutOrderTool",
                intent="INSTANT_CHECKOUT_ORDER",
                node_type="TRANSACTIONAL",
                bound_slots=dict(parsed.slots),
                missing_slots=[],
            )
            if "location" in new_frame.bound_slots and "delivery_zone" not in new_frame.bound_slots:
                new_frame.bound_slots["delivery_zone"] = new_frame.bound_slots["location"]

            tool_res = await get_local_tool_dispatcher().evaluate(
                intent="INSTANT_CHECKOUT_ORDER",
                slots=new_frame.bound_slots,
                catalog_manifest=catalog_manifest,
            )
            if tool_res:
                envelope = await cls._format_tool_evaluation_envelope(
                    merchant_id=m_id,
                    customer_phone=customer_phone,
                    merchant_name=merchant_name,
                    stack=stack,
                    active_frame=new_frame,
                    tool_res=tool_res,
                    session=session,
                )
                top = stack.peek()
                latency = (time.perf_counter() - start_time) * 1000.0
                return FSMTurnOutcome(
                    transition=FSMTransitionType.NEW_FLOW,
                    envelope=envelope,
                    intent="INSTANT_CHECKOUT_ORDER",
                    action=cls._strategy_to_action(envelope.strategy),
                    lead_tier=parsed.lead_tier,
                    urgency_score=parsed.urgency_score,
                    confidence=parsed.confidence,
                    detected_dialect=parsed.detected_dialect,
                    routing_source="FAST_PATH",
                    extracted_entities=dict(new_frame.bound_slots),
                    tokens_consumed=parsed.tokens_consumed,
                    latency_ms=round(latency, 2),
                    active_frame=top.model_dump(mode="json") if top else None,
                    context_stack=[f.model_dump(mode="json") for f in stack.frames],
                )

        nlu_resp = await cls._run_cascading_nlu(
            merchant_id=merchant_id,
            text=sanitized_text,
            customer_phone=customer_phone,
            customer_name=customer_name,
            recent_history=recent_history,
            session=session,
            merchant_name=merchant_name,
            custom_dictionary=custom_dictionary,
            catalog_manifest=catalog_manifest,
            provider_context=provider_context,
        )

        if nlu_resp.action == "DISPATCH_CLARIFICATION":
            new_frame = NegotiationFrame(
                merchant_id=m_id,
                active_tool="CheckoutOrderTool",
                intent=nlu_resp.intent,
                node_type="TRANSACTIONAL",
                bound_slots=nlu_resp.extracted_entities.get("bound_slots", {}),
                missing_slots=nlu_resp.extracted_entities.get("missing_slots", []),
            )
            stack.push(new_frame)
            await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

        envelope = await ResponseOrchestrator.resolve(
            merchant_id=merchant_id,
            nlu_result=nlu_resp,
            customer_phone=customer_phone,
            raw_message=sanitized_text,
            session=session,
            merchant_name=merchant_name,
        )

        if envelope and envelope.strategy in (
            ResponseStrategy.CATALOG_PRODUCT_LIST,
            ResponseStrategy.SINGLE_PRODUCT_QUOTE,
            ResponseStrategy.FULL_CATALOG_BROWSE,
        ):
            target_prod = nlu_resp.extracted_entities.get("product") or ""
            atomic_bound_slots = {
                k: nlu_resp.extracted_entities[k]
                for k in ("offering_id", "sku", "product", "product_name")
                if nlu_resp.extracted_entities.get(k) is not None
            }
            top_frame = NegotiationFrame(
                merchant_id=m_id,
                active_tool="ProductCatalog",
                intent=nlu_resp.intent,
                node_type="ATOMIC_QUERY",
                bound_slots=atomic_bound_slots,
                missing_slots=[],
                pending_offer={
                    "action": "SHOW_PRICES",
                    "product": target_prod,
                    "strategy": envelope.strategy.value,
                },
            )
            stack.push(top_frame)
            await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

        top = stack.peek()
        latency = (time.perf_counter() - start_time) * 1000.0
        return FSMTurnOutcome(
            transition=FSMTransitionType.NEW_FLOW,
            envelope=envelope,
            intent=nlu_resp.intent,
            action=nlu_resp.action or "STANDARD_REPLY",
            lead_tier=nlu_resp.lead_tier,
            urgency_score=nlu_resp.urgency_score,
            confidence=nlu_resp.confidence,
            detected_dialect=nlu_resp.detected_dialect,
            routing_source=nlu_resp.routing_source,
            extracted_entities=nlu_resp.extracted_entities,
            tokens_consumed=nlu_resp.tokens_consumed + parsed.tokens_consumed,
            latency_ms=round(max(nlu_resp.latency_ms, latency), 2),
            active_frame=top.model_dump(mode="json") if top else None,
            context_stack=[f.model_dump(mode="json") for f in stack.frames],
        )

    # -------------------------------------------------------------------------
    # INTERNAL FSM HELPERS
    # -------------------------------------------------------------------------
    @classmethod
    async def _resolve_independent_inquiry(
        cls,
        merchant_id: str,
        customer_phone: str,
        session: Optional[AsyncSession],
        merchant_name: str,
        catalog_manifest: Optional[str],
        parsed: ParsedTurnInput,
        active_frame: Optional[NegotiationFrame],
        stack: ContextStack,
        start_time: float,
    ) -> Optional[FSMTurnOutcome]:
        """
        Answers a knowledge-bound FAQ strictly from the merchant knowledge base.

        Returns None when the knowledge base holds no reference (ungrounded) so the caller
        escalates to Stage 2/3 instead of fabricating an answer or opening an agent ticket.
        The LIFO stack is never modified; an in-progress checkout is merely re-prompted.
        """
        try:
            merchant_uuid = UUID(merchant_id)
        except ValueError:
            return None

        # Dedicated post-purchase order status tracking lane (ADR-0048)
        if parsed.intent == "ORDER_STATUS_INQUIRY":
            inquiry_res = await CustomerOrderLedger.lookup_order_for_inquiry(
                merchant_id=merchant_id,
                customer_phone=customer_phone,
                order_ref=parsed.slots.get("order_reference"),
                session=session,
            )
            order_envelope = ResponseFormatter.format_order_status_card(
                to_phone=customer_phone,
                order=inquiry_res.order,
                multiple_orders=inquiry_res.orders if inquiry_res.cardinality == "MULTIPLE" else None,
                merchant_name=merchant_name,
            )

            if active_frame and active_frame.missing_slots:
                tool_res = await get_local_tool_dispatcher().evaluate(
                    intent=active_frame.intent,
                    slots=active_frame.bound_slots,
                    catalog_manifest=catalog_manifest,
                )
                if tool_res and tool_res.clarification:
                    cart_desc = f"{active_frame.bound_slots.get('quantity', 1)}x {active_frame.bound_slots.get('product_name') or active_frame.bound_slots.get('product') or 'items'}"
                    total_str = f" (₦{tool_res.calculated_total_kobo // 100:,})" if tool_res.calculated_total_kobo else ""
                    resumption_prompt = f"🛒 Continuing your reservation for *{cart_desc}*{total_str}:\n{tool_res.clarification.prompt_text}"
                    envelope = ResponseFormatter.format_compound_response(
                        to_phone=customer_phone,
                        answer_text=order_envelope.body_text,
                        resumption_prompt=resumption_prompt,
                        buttons=tool_res.clarification.buttons,
                        strategy=ResponseStrategy.ORDER_STATUS_CARD,
                    )
                else:
                    envelope = order_envelope
            else:
                envelope = order_envelope

            top = stack.peek()
            latency = (time.perf_counter() - start_time) * 1000.0
            return FSMTurnOutcome(
                transition=FSMTransitionType.INDEPENDENT_INQUIRY,
                envelope=envelope,
                intent="ORDER_STATUS_INQUIRY",
                action="RESOLVE_ORDER_STATUS",
                lead_tier="HOT",
                urgency_score=8,
                confidence=parsed.confidence,
                detected_dialect=parsed.detected_dialect,
                routing_source="ORDER_LEDGER",
                extracted_entities=parsed.slots,
                tokens_consumed=parsed.tokens_consumed,
                latency_ms=round(latency, 2),
                active_frame=top.model_dump(mode="json") if top else None,
                context_stack=[f.model_dump(mode="json") for f in stack.frames],
            )

        if session is None:
            return None

        entries = await KnowledgeService.search_faq_entries(
            session=session,
            merchant_id=merchant_uuid,
            intent=parsed.intent,
        )
        if not entries:
            logger.info("independent_inquiry_ungrounded", merchant_id=merchant_id, intent=parsed.intent)
            return None

        kb_text = "\n".join(e.content.strip() for e in entries)
        lead_in = ""
        if parsed.intent == "DELIVERY_TIMELINE_INQUIRY":
            mentioned_zone = parsed.slots.get("delivery_zone") or parsed.slots.get("location")
            orders = await CustomerOrderLedger.list_recent(merchant_id, customer_phone, session=session)
            if mentioned_zone:
                lead_in = f"For delivery to {mentioned_zone}:\n"
            elif orders:
                latest = orders[0]
                where = f" to {latest.delivery_zone}" if latest.delivery_zone else ""
                lead_in = f"For your most recent order ({latest.order_summary}{where}):\n"
                if len(orders) > 1:
                    kb_text += "\n\n*(Note: You have multiple recent orders. If you are inquiring about an older order, please specify its item or location.)*"

        reply = f"{lead_in}{kb_text}"
        buttons = None

        # If a checkout is mid-flight, format compound response to resume without dropping stack (ADR-0048)
        if active_frame and active_frame.missing_slots:
            tool_res = await get_local_tool_dispatcher().evaluate(
                intent=active_frame.intent,
                slots=active_frame.bound_slots,
                catalog_manifest=catalog_manifest,
            )
            if tool_res and tool_res.clarification:
                cart_desc = f"{active_frame.bound_slots.get('quantity', 1)}x {active_frame.bound_slots.get('product_name') or active_frame.bound_slots.get('product') or 'items'}"
                total_str = f" (₦{tool_res.calculated_total_kobo // 100:,})" if tool_res.calculated_total_kobo else ""
                resumption_prompt = f"🛒 Continuing your reservation for *{cart_desc}*{total_str}:\n{tool_res.clarification.prompt_text}"
                envelope = ResponseFormatter.format_compound_response(
                    to_phone=customer_phone,
                    answer_text=reply,
                    resumption_prompt=resumption_prompt,
                    buttons=tool_res.clarification.buttons,
                    strategy=ResponseStrategy.STANDARD_TEXT,
                )
            else:
                envelope = ResponseFormatter.format_standard_text(
                    to_phone=customer_phone,
                    text=reply,
                    strategy=ResponseStrategy.STANDARD_TEXT,
                )
        else:
            envelope = ResponseFormatter.format_standard_text(
                to_phone=customer_phone,
                text=reply,
                strategy=ResponseStrategy.STANDARD_TEXT,
            )

        top = stack.peek()
        latency = (time.perf_counter() - start_time) * 1000.0
        return FSMTurnOutcome(
            transition=FSMTransitionType.INDEPENDENT_INQUIRY,
            envelope=envelope,
            intent=parsed.intent,
            action="ANSWER_FROM_KNOWLEDGE_BASE",
            lead_tier=parsed.lead_tier,
            urgency_score=parsed.urgency_score,
            confidence=parsed.confidence,
            detected_dialect=parsed.detected_dialect,
            routing_source="CUSTOM_LOCAL_MODEL",
            extracted_entities=dict(parsed.slots),
            tokens_consumed=parsed.tokens_consumed,
            latency_ms=round(latency, 2),
            active_frame=top.model_dump(mode="json") if top else None,
            context_stack=[f.model_dump(mode="json") for f in stack.frames],
        )

    @classmethod
    async def _execute_push_subflow_and_pop_resume(
        cls,
        merchant_id: Union[UUID, str],
        customer_phone: str,
        customer_name: str,
        sanitized_text: str,
        recent_history: Optional[Sequence[Union[DialogueTurn, str]]],
        session: Optional[AsyncSession],
        merchant_name: str,
        custom_dictionary: Optional[List[Dict[str, Any]]],
        catalog_manifest: Optional[str],
        provider_context: Optional[Dict[str, Any]],
        stack: ContextStack,
        suspended_frame: NegotiationFrame,
        parsed: ParsedTurnInput,
        start_time: float,
    ) -> FSMTurnOutcome:
        """
        LIFO Context Switch Execution:
        1. Preserves suspended_frame (e.g. CHECKOUT) on stack and pushes temporary sub-flow frame.
        2. Resolves sub-flow response via CascadingNLUPipeline + ResponseOrchestrator.
        3. If sub-flow is HUMAN_AGENT_HANDOFF, leaves handoff active on top of stack.
        4. Otherwise pops sub-flow frame -> restores CHECKOUT frame -> hydrates combined response via Function B.
        """
        m_id = str(merchant_id)
        stack.push(suspended_frame)

        subflow_frame = NegotiationFrame(
            merchant_id=m_id,
            active_tool="SubflowResolver",
            intent=parsed.intent,
            node_type="HANDOFF" if parsed.intent in ("HUMAN_AGENT_HANDOFF", "DISPATCH_AGENT_HANDOFF") else "ATOMIC_QUERY",
            bound_slots=dict(parsed.slots),
            missing_slots=[],
        )
        stack.push(subflow_frame)
        await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

        # Execute sub-flow query using Function A's parsed intent when high confidence
        if parsed.confidence >= 0.75 and parsed.intent in (
            "ORDER_STATUS_INQUIRY",
            "DELIVERY_TIMELINE_INQUIRY",
            "TRUST_VERIFICATION_PROOF",
            "WHOLESALE_DISCOUNT_INQUIRY",
            "REQUEST_PAYMENT_DETAILS",
            "PRICE_INQUIRY",
            "SHOW_PRODUCT_CATALOG",
            "HUMAN_AGENT_HANDOFF",
            "DISPATCH_AGENT_HANDOFF",
        ):
            from app.contexts.ingress.schemas import NLUClassificationResponse

            suggested = (
                None
                if parsed.intent in ("PRICE_INQUIRY", "SHOW_PRODUCT_CATALOG", "ORDER_STATUS_INQUIRY")
                else (
                    "A human agent will be with you shortly."
                    if parsed.intent in ("HUMAN_AGENT_HANDOFF", "DISPATCH_AGENT_HANDOFF")
                    else synthesize_custom_model_reply(
                        intent=parsed.intent,
                        dialect=parsed.detected_dialect,
                        entities=parsed.slots,
                        merchant_name=merchant_name,
                    )
                )
            )
            sub_action = (
                "DISPATCH_AGENT_HANDOFF"
                if parsed.intent in ("HUMAN_AGENT_HANDOFF", "DISPATCH_AGENT_HANDOFF")
                else (
                    "RESOLVE_ORDER_STATUS"
                    if parsed.intent == "ORDER_STATUS_INQUIRY"
                    else ("SHOW_PRODUCT_CATALOG" if parsed.intent in ("PRICE_INQUIRY", "SHOW_PRODUCT_CATALOG") else "SUBFLOW_RESOLVED_WITH_RESUME")
                )
            )
            nlu_resp = NLUClassificationResponse(
                routing_source="CUSTOM_LOCAL_MODEL",
                intent=parsed.intent,
                lead_tier=parsed.lead_tier,
                urgency_score=parsed.urgency_score,
                confidence=parsed.confidence,
                detected_dialect=parsed.detected_dialect,
                suggested_reply=suggested or f"Thank you for contacting {merchant_name}!",
                action=sub_action,
                extracted_entities=parsed.slots,
                latency_ms=parsed.latency_ms,
                tokens_consumed=parsed.tokens_consumed,
                estimated_kobo_saved=52000,
            )
        else:
            nlu_resp = await cls._run_cascading_nlu(
                merchant_id=merchant_id,
                text=sanitized_text,
                customer_phone=customer_phone,
                customer_name=customer_name,
                recent_history=recent_history,
                session=session,
                merchant_name=merchant_name,
                custom_dictionary=custom_dictionary,
                catalog_manifest=catalog_manifest,
                provider_context=provider_context,
            )

        subflow_envelope = await ResponseOrchestrator.resolve(
            merchant_id=merchant_id,
            nlu_result=nlu_resp,
            customer_phone=customer_phone,
            raw_message=sanitized_text,
            session=session,
            merchant_name=merchant_name,
        )

        # If customer explicitly escalated to a human agent, do not pop back to bot checkout prompt
        if nlu_resp.action == "DISPATCH_AGENT_HANDOFF" or subflow_envelope.strategy == ResponseStrategy.AGENT_HANDOFF:
            top = stack.peek()
            latency = (time.perf_counter() - start_time) * 1000.0
            return FSMTurnOutcome(
                transition=FSMTransitionType.PUSH_SUBFLOW_AND_POP_RESUME,
                envelope=subflow_envelope,
                intent=nlu_resp.intent,
                action="DISPATCH_AGENT_HANDOFF",
                lead_tier=nlu_resp.lead_tier,
                urgency_score=nlu_resp.urgency_score,
                confidence=nlu_resp.confidence,
                detected_dialect=nlu_resp.detected_dialect,
                routing_source=nlu_resp.routing_source,
                extracted_entities=nlu_resp.extracted_entities,
                tokens_consumed=nlu_resp.tokens_consumed + parsed.tokens_consumed,
                latency_ms=round(latency, 2),
                active_frame=top.model_dump(mode="json") if top else None,
                context_stack=[f.model_dump(mode="json") for f in stack.frames],
            )

        # Sub-flow completed: POP sub-flow from LIFO stack -> expose suspended_frame at top
        stack.pop()
        resumed_frame = stack.peek() or suspended_frame
        resumed_frame.refresh_ttl()
        stack.push(resumed_frame)
        await NegotiationFrameManager.save_stack(m_id, customer_phone, stack)

        # Evaluate resumed frame against CheckoutOrderTool to get exact missing-slot prompt & buttons
        tool_res = await get_local_tool_dispatcher().evaluate(
            intent=resumed_frame.intent,
            slots=resumed_frame.bound_slots,
            catalog_manifest=catalog_manifest,
        )
        clarification_prompt = (
            tool_res.clarification.prompt_text
            if tool_res and tool_res.clarification
            else ""
        )
        clarification_buttons = (
            tool_res.clarification.buttons
            if tool_res and tool_res.clarification
            else None
        )

        # Function B: Stateless Output Translation with Dynamic Prompt Hydration
        open_weight = get_open_weight_adapter()
        hydration_out = await open_weight.translate_output(
            HydrationTranslationInput(
                primary_intent=nlu_resp.intent,
                verified_facts=nlu_resp.extracted_entities,
                fallback_body_text=subflow_envelope.body_text,
                resumed_frame={
                    "intent": resumed_frame.intent,
                    "bound_slots": resumed_frame.bound_slots,
                    "missing_slots": resumed_frame.missing_slots,
                    "clarification_prompt": clarification_prompt,
                },
                target_dialect=parsed.detected_dialect,
                merchant_name=merchant_name,
            )
        )

        # Preserve interactive list if sub-flow returned a catalog list; otherwise attach resumed frame's buttons
        if subflow_envelope.message_type == EgressMessageType.INTERACTIVE_LIST:
            subflow_envelope.body_text = hydration_out.translated_text
            final_envelope = subflow_envelope
        elif clarification_buttons:
            final_envelope = ResponseFormatter.format_interactive_buttons(
                to_phone=customer_phone,
                body_text=hydration_out.translated_text,
                buttons=clarification_buttons,
                strategy=subflow_envelope.strategy,
            )
        else:
            subflow_envelope.body_text = hydration_out.translated_text
            final_envelope = subflow_envelope

        total_tokens = parsed.tokens_consumed + nlu_resp.tokens_consumed + hydration_out.tokens_consumed
        latency = (time.perf_counter() - start_time) * 1000.0

        return FSMTurnOutcome(
            transition=FSMTransitionType.PUSH_SUBFLOW_AND_POP_RESUME,
            envelope=final_envelope,
            intent=nlu_resp.intent,
            action=nlu_resp.action or "SUBFLOW_RESOLVED_WITH_RESUME",
            lead_tier=nlu_resp.lead_tier,
            urgency_score=nlu_resp.urgency_score,
            confidence=nlu_resp.confidence,
            detected_dialect=nlu_resp.detected_dialect,
            routing_source=nlu_resp.routing_source,
            extracted_entities=nlu_resp.extracted_entities,
            tokens_consumed=total_tokens,
            latency_ms=round(latency, 2),
            active_frame=resumed_frame.model_dump(mode="json"),
            context_stack=[f.model_dump(mode="json") for f in stack.frames],
        )

    @staticmethod
    def _detect_slot_mutation(active_frame: NegotiationFrame, parsed: ParsedTurnInput) -> bool:
        if parsed.slot_mutations:
            return True
        bound = active_frame.bound_slots
        slots = parsed.slots
        # Check if customer supplied a different product/SKU/offering_id than the one already bound
        if bound.get("offering_id") and slots.get("offering_id") and str(bound["offering_id"]).lower() != str(slots["offering_id"]).lower():
            return True
        if bound.get("product") and slots.get("product") and bound["product"].lower() != str(slots["product"]).lower():
            return True
        if bound.get("sku") and slots.get("sku") and bound["sku"].upper() != str(slots["sku"]).upper():
            return True
        return False

    @staticmethod
    def _provides_relevant_checkout_slot(active_frame: NegotiationFrame, parsed: ParsedTurnInput) -> bool:
        if parsed.intent in (
            "DELIVERY_TIMELINE_INQUIRY",
            "ORDER_STATUS_INQUIRY",
            "TRUST_VERIFICATION_PROOF",
            "WHOLESALE_DISCOUNT_INQUIRY",
            "HUMAN_AGENT_HANDOFF",
            "DISPATCH_AGENT_HANDOFF",
            "RESERVE_APPOINTMENT",
            "CONFIRM_PAYMENT",
            "PRICE_INQUIRY",
        ):
            return False
        relevant_keys = {"offering_id", "sku", "product", "product_name", "quantity", "location", "delivery_zone", "fulfillment_type", "line_items"}
        return bool(relevant_keys.intersection(parsed.slots.keys()))

    @staticmethod
    def _apply_slots_to_frame(
        active_frame: NegotiationFrame,
        parsed: ParsedTurnInput,
        is_mutation: bool = False,
    ) -> None:
        merged_updates = {**parsed.slots, **parsed.slot_mutations}
        if is_mutation:
            # If product, SKU, or offering_id changed, invalidate stale bound SKU & pricing
            new_prod = (merged_updates.get("product") or "").lower()
            old_prod = (active_frame.bound_slots.get("product") or "").lower()
            new_sku = (merged_updates.get("sku") or "").upper()
            old_sku = (active_frame.bound_slots.get("sku") or "").upper()
            new_off = (merged_updates.get("offering_id") or "").lower()
            old_off = (active_frame.bound_slots.get("offering_id") or "").lower()
            if (
                (new_prod and new_prod != old_prod)
                or (new_sku and new_sku != old_sku)
                or (new_off and new_off != old_off)
            ):
                for stale_key in ("offering_id", "sku", "product_name", "unit_price_kobo", "in_stock", "line_items"):
                    active_frame.bound_slots.pop(stale_key, None)

        for k, v in merged_updates.items():
            if v is not None:
                active_frame.bound_slots[k] = v
        if "location" in merged_updates and "delivery_zone" not in merged_updates:
            active_frame.bound_slots["delivery_zone"] = merged_updates["location"]

    @staticmethod
    async def _bind_and_validate_sku(
        merchant_id: Union[UUID, str],
        customer_phone: str,
        sku_val: str,
        active_frame: NegotiationFrame,
        session: Optional[AsyncSession],
        catalog_manifest: Optional[str],
    ) -> Optional[EgressPayloadEnvelope]:
        m_id = str(merchant_id)
        offering = await KnowledgeService.get_offering_by_sku(
            merchant_id=merchant_id,
            sku=sku_val,
            session=session,
        )
        if offering:
            stock_qty = (
                offering.metadata.get("stock_quantity")
                if isinstance(getattr(offering, "metadata", None), dict)
                else None
            )
            if not offering.is_available or (stock_qty is not None and stock_qty <= 0):
                await NegotiationFrameManager.evict_frame(m_id, customer_phone)
                prompt = (
                    f"Apologies, *{offering.title}* is currently out of stock.\n\n"
                    f"Would you like to browse our available items or speak directly with our team?"
                )
                return ResponseFormatter.format_interactive_buttons(
                    to_phone=customer_phone,
                    body_text=prompt,
                    buttons=[
                        {"id": "SHOW_CATALOG", "title": "View Catalog"},
                        {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
                    ],
                    strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
                )
            active_frame.bound_slots["offering_id"] = offering.offering_id
            active_frame.bound_slots["sku"] = offering.sku
            active_frame.bound_slots["product_name"] = offering.title
            active_frame.bound_slots["unit_price_kobo"] = offering.price_kobo
            active_frame.bound_slots["in_stock"] = True
            return None

        from app.contexts.knowledge.offering_schemas import compute_offering_id
        from app.core.generation.tools import DEFAULT_COMMODITY_CATALOG, parse_catalog_manifest
        catalog_to_check = parse_catalog_manifest(catalog_manifest) if catalog_manifest else DEFAULT_COMMODITY_CATALOG
        matched = [
            item for item in catalog_to_check
            if item.get("sku", "").upper() == str(sku_val).upper()
            or compute_offering_id(m_id, item.get("sku", "")).lower() == str(sku_val).lower()
            or compute_offering_id(None, item.get("sku", "")).lower() == str(sku_val).lower()
        ]
        if matched:
            matched_item = matched[0]
            if matched_item.get("in_stock") is False:
                await NegotiationFrameManager.evict_frame(m_id, customer_phone)
                item_name = matched_item.get("name") or sku_val.replace("_", " ").title()
                prompt = (
                    f"Apologies, *{item_name}* is currently out of stock.\n\n"
                    f"Would you like to browse our available items or speak directly with our team?"
                )
                return ResponseFormatter.format_interactive_buttons(
                    to_phone=customer_phone,
                    body_text=prompt,
                    buttons=[
                        {"id": "SHOW_CATALOG", "title": "View Catalog"},
                        {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
                    ],
                    strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
                )
            active_frame.bound_slots["offering_id"] = compute_offering_id(m_id, matched_item["sku"])
            active_frame.bound_slots["sku"] = matched_item["sku"]
            active_frame.bound_slots["product_name"] = matched_item["name"]
            active_frame.bound_slots["unit_price_kobo"] = matched_item["price_kobo"]
            active_frame.bound_slots["in_stock"] = True
        else:
            active_frame.bound_slots["sku"] = sku_val
        return None

    @staticmethod
    async def _format_tool_evaluation_envelope(
        merchant_id: str,
        customer_phone: str,
        merchant_name: str,
        stack: ContextStack,
        active_frame: NegotiationFrame,
        tool_res: Any,
        session: Optional[AsyncSession] = None,
    ) -> EgressPayloadEnvelope:
        if tool_res.status == ToolStatus.NEEDS_CLARIFICATION:
            active_frame.missing_slots = tool_res.missing_slots
            if tool_res.bound_slots:
                active_frame.bound_slots.update(tool_res.bound_slots)
            stack.push(active_frame)
            await NegotiationFrameManager.save_stack(merchant_id, customer_phone, stack)
            prompt = tool_res.clarification.prompt_text if tool_res.clarification else "Please choose an option."
            buttons = tool_res.clarification.buttons if tool_res.clarification else None
            if buttons and isinstance(buttons, list) and len(buttons) > 0:
                return ResponseFormatter.format_interactive_buttons(
                    to_phone=customer_phone,
                    body_text=prompt,
                    buttons=buttons,
                    strategy=ResponseStrategy.SLOT_CLARIFICATION,
                )
            return ResponseFormatter.format_standard_text(
                to_phone=customer_phone,
                text=prompt,
                strategy=ResponseStrategy.SLOT_CLARIFICATION,
            )

        if tool_res.status == ToolStatus.CONVERGED:
            if tool_res.bound_slots:
                active_frame.bound_slots.update(tool_res.bound_slots)
            active_frame.bound_slots["calculated_total_kobo"] = tool_res.calculated_total_kobo or 0
            stack.pop()
            await NegotiationFrameManager.save_stack(merchant_id, customer_phone, stack)
            total_kobo = tool_res.calculated_total_kobo or 0
            # Persist a stack-independent order pointer in PostgreSQL (ledger.customer_orders)
            await CustomerOrderLedger.record_order(
                merchant_id=merchant_id,
                customer_phone=customer_phone,
                bound_slots=active_frame.bound_slots,
                total_kobo=total_kobo,
                session=session,
            )
            total_naira = f"₦{total_kobo // 100:,}"
            loc_str = (
                f" for delivery to {tool_res.bound_slots.get('delivery_zone', 'your address')}"
                if tool_res.bound_slots.get("fulfillment_type") == "EXPRESS_DELIVERY"
                else " for warehouse self-pickup"
            )
            line_items = tool_res.bound_slots.get("line_items")
            if isinstance(line_items, list) and len(line_items) > 1:
                order_summary = tool_res.bound_slots.get("product_name", "bulk items")
            else:
                order_summary = f"{tool_res.bound_slots.get('quantity', 1)}x {tool_res.bound_slots.get('product_name', 'item')}"
            reply = (
                f"Sharp! We don reserve your order ({order_summary}){loc_str}.\n"
                f"Total Amount: *{total_naira}* (10-minute anti-ghosting hold).\n\n"
                f"🏦 *Payment Details (Dedicated Virtual NUBAN):*\n"
                f"Bank: *Moniepoint MFB*\n"
                f"Account Name: *{merchant_name}*\n"
                f"Account Number: *9031842901*\n\n"
                f"Once transfer clear, receipt go land here sharp sharp!"
            )
            return ResponseFormatter.format_standard_text(
                to_phone=customer_phone,
                text=reply,
                strategy=ResponseStrategy.CHECKOUT_CONVERGED,
            )

        # OUT_OF_STOCK or REJECTED
        stack.pop()
        await NegotiationFrameManager.save_stack(merchant_id, customer_phone, stack)
        prompt = tool_res.clarification.prompt_text if tool_res.clarification else "Sorry, out of stock."
        buttons = tool_res.clarification.buttons if tool_res.clarification else None
        if buttons and isinstance(buttons, list) and len(buttons) > 0:
            return ResponseFormatter.format_interactive_buttons(
                to_phone=customer_phone,
                body_text=prompt,
                buttons=buttons,
                strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
            )
        return ResponseFormatter.format_standard_text(
            to_phone=customer_phone,
            text=prompt,
            strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
        )

    @staticmethod
    def _strategy_to_action(strategy: ResponseStrategy) -> str:
        mapping = {
            ResponseStrategy.CHECKOUT_CONVERGED: "GENERATE_VIRTUAL_NUBAN_HOLD",
            ResponseStrategy.OUT_OF_STOCK_ALERT: "OUT_OF_STOCK_ALERT",
            ResponseStrategy.SINGLE_PRODUCT_QUOTE: "DISPLAY_PRODUCT_DETAIL_CARD",
            ResponseStrategy.CATALOG_PRODUCT_LIST: "DISPLAY_CATALOG_LIST",
            ResponseStrategy.AGENT_HANDOFF: "AGENT_HANDOFF",
            ResponseStrategy.SLOT_CLARIFICATION: "DISPATCH_CLARIFICATION",
            ResponseStrategy.ORDER_STATUS_CARD: "RESOLVE_ORDER_STATUS",
            ResponseStrategy.UNRESOLVED_DISAMBIGUATION: "SHOW_DISAMBIGUATION_MENU",
        }
        return mapping.get(strategy, "DISPATCH_CLARIFICATION")

    @staticmethod
    def _resolve_interactive_intent(
        interactive_id: str,
        strategy: ResponseStrategy,
        active_frame: Optional[NegotiationFrame],
    ) -> str:
        if strategy == ResponseStrategy.OUT_OF_STOCK_ALERT:
            return "OUT_OF_STOCK_ALERT"
        envelope = InteractiveProtocolEnvelope.model_validate(interactive_id)
        match envelope.event:
            case SlotBindAction():
                return "INSTANT_CHECKOUT_ORDER"
            case ProductTapAction():
                return "PRICE_INQUIRY"
            case CommandTapAction(command="SHOW_CATALOG"):
                return "SHOW_PRODUCT_CATALOG"
            case CommandTapAction(command="AGENT_HANDOFF"):
                return "DISPATCH_AGENT_HANDOFF"
        return active_frame.intent if active_frame else "INSTANT_CHECKOUT_ORDER"
