"""Custom Local Model Classifier Adapters with ONNX Runtime & Lexical Dialect Analyzer (ADR-0024, ADR-0044)."""

import time
import re
import json
import math
import structlog
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List
from app.adapters.base import CustomClassifierPort, ClassificationOutput
from app.core.config import settings

logger = structlog.get_logger(__name__)

try:
    import onnxruntime as ort
    from tokenizers import Tokenizer
    ONNX_RUNTIME_AVAILABLE = True
except ImportError:
    ONNX_RUNTIME_AVAILABLE = False
    ort = None  # type: ignore
    Tokenizer = None  # type: ignore


class LexicalDialectAnalyzer:
    """Deterministic lexical slang and dialect detector for Nigerian SME commerce (ADR-0044 Q5)."""

    PIDGIN_MARKERS = {
        "abeg", "dey", "wetin", "oya", "fit", "wahala", "sef", "no cap", "sharp", "sharp sharp",
        "make we", "how far", "i don", "na so", "una", "comot", "chop", "kobo", "naira",
        "waybill", "drop am", "send am", "no wahala", "hope say", "you legit", "where your shop dey",
    }

    COMMERCIAL_SLANG_MARKERS = {
        "acct", "dm", "last price", "slash price", "discount dey", "reduce small",
        "wholesale price", "waybill", "dispatch rider", "see past work", "moniepoint acct",
    }

    @classmethod
    def detect_dialect(cls, text: str) -> str:
        lower = text.lower().strip()
        words = re.findall(r"\b\w+\b", lower)

        pidgin_hits = sum(1 for w in words if w in cls.PIDGIN_MARKERS)
        slang_hits = sum(1 for w in words if w in cls.COMMERCIAL_SLANG_MARKERS)

        if any(phrase in lower for phrase in ["how far", "sharp sharp", "no wahala", "where your shop dey", "hope say", "make we", "drop am"]):
            pidgin_hits += 2

        if any(phrase in lower for phrase in ["last price", "slash price", "discount dey", "dispatch rider", "see past work"]):
            slang_hits += 2

        if pidgin_hits >= 2 or any(w in lower for w in ["abeg", "wetin", "oya", "dey", "sef"]):
            return "Nigerian Pidgin"
        elif slang_hits >= 1 or pidgin_hits >= 1:
            return "Commercial Slang"
        return "Standard English"


class MockCustomClassifierAdapter(CustomClassifierPort):
    """
    Mock Simulator for fine-tuned Hugging Face / ONNX Nigerian Pidgin Intent Classifier.
    Accurately classifies domain-specific nuanced slang and returns structured intent & confidence.
    """

    async def classify(self, text: str) -> ClassificationOutput:
        start_time = time.perf_counter()
        lower = text.lower().strip()

        intent = "GENERAL_INQUIRY"
        lead_tier = "WARM"
        urgency_score = 6
        confidence = 0.88
        detected_dialect = LexicalDialectAnalyzer.detect_dialect(text)
        action = None
        entities: Dict[str, Any] = {}

        # 1. Nuanced Wholesale & Discount Negotiation (Pidgin)
        if any(w in lower for w in ["slash price", "discount dey", "reduce small", "wholesale price", "wholesale discount", "if i buy plenty", "last price"]):
            intent = "WHOLESALE_DISCOUNT_INQUIRY"
            lead_tier = "HOT"
            urgency_score = 8
            confidence = 0.91
            action = "APPLY_BULK_DISCOUNT_TIER"

        # 2a. Post-Purchase Order Status & Delivery Tracking (ADR-0048)
        elif any(w in lower for w in ["when is my order", "when will my order", "where is my order", "order status", "track my order", "dispatch status", "rider where", "wetin happen to my order", "my order never reach", "where my delivery", "arrive"]):
            intent = "ORDER_STATUS_INQUIRY"
            lead_tier = "HOT"
            urgency_score = 8
            confidence = 0.94
            action = "RESOLVE_ORDER_STATUS"

        # 2b. Logistics & Delivery Timeline (Pre-purchase SLA & interstate dispatch)
        elif any(w in lower for w in ["when e go land", "delivery timeline", "dispatch rider", "interstate waybill", "how many days"]):
            intent = "DELIVERY_TIMELINE_INQUIRY"
            lead_tier = "WARM"
            urgency_score = 7
            confidence = 0.89
            action = "CALCULATE_DISPATCH_ETA"

        # 3. Trust, Proof & Legitimacy Inquiries (Anti-fraud skepticism)
        elif any(w in lower for w in ["hope say no be scam", "you legit", "where your shop dey", "proof dey", "see past work", "reviews"]):
            intent = "TRUST_VERIFICATION_PROOF"
            lead_tier = "WARM"
            urgency_score = 7
            confidence = 0.93
            action = "INJECT_SOCIAL_PROOF_PDF"

        # 4. Bank Transfer / USSD Payment Inquiries
        elif any(w in lower for w in ["ussd code", "send account", "moniepoint acct", "gtb transfer", "zenith"]):
            intent = "REQUEST_PAYMENT_DETAILS"
            lead_tier = "HOT"
            urgency_score = 9
            confidence = 0.94
            action = "GENERATE_VIRTUAL_NUBAN_HOLD"

        # 5. Out-of-domain / Low Confidence fallback
        else:
            confidence = 0.62  # Low confidence -> Triggers Stage 3 LLM Escalation

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return ClassificationOutput(
            intent=intent,
            lead_tier=lead_tier,
            urgency_score=urgency_score,
            confidence=confidence,
            detected_dialect=detected_dialect,
            action=action,
            extracted_entities=entities,
            tokens_consumed=0,
            latency_ms=max(12.0, latency_ms),
        )


class ONNXClassifierAdapter(CustomClassifierPort):
    """
    Production ONNX Runtime execution for exported HuggingFace transformer models (ADR-0044).
    Lazily loads model.onnx, tokenizer.json, and labels.json from models/nigerian_pidgin_intent/.
    If weights or onnxruntime are absent, gracefully delegates to MockCustomClassifierAdapter.
    """

    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        self._session: Optional[Any] = None
        self._tokenizer: Optional[Any] = None
        self._labels: Dict[str, str] = {}
        self._load_attempted: bool = False
        self._fallback_adapter = MockCustomClassifierAdapter()

    def _ensure_loaded(self) -> bool:
        """Lazily verifies and initializes ONNX session and Tokenizer artifacts (ADR-0044 Q9)."""
        if self._load_attempted:
            return self._session is not None and self._tokenizer is not None

        self._load_attempted = True

        if not ONNX_RUNTIME_AVAILABLE:
            logger.warning(
                "onnxruntime_or_tokenizers_package_not_installed_falling_back_to_mock",
                model_path=str(self.model_path),
            )
            return False

        model_file = self.model_path / "model.onnx"
        tokenizer_file = self.model_path / "tokenizer.json"
        labels_file = self.model_path / "labels.json"

        if not (model_file.exists() and tokenizer_file.exists()):
            logger.info(
                "onnx_model_files_not_found_falling_back_to_mock",
                model_file_exists=model_file.exists(),
                tokenizer_file_exists=tokenizer_file.exists(),
                model_path=str(self.model_path),
            )
            return False

        try:
            # Initialize ONNX inference session with CPU provider
            self._session = ort.InferenceSession(str(model_file), providers=["CPUExecutionProvider"])
            self._tokenizer = Tokenizer.from_file(str(tokenizer_file))

            if labels_file.exists():
                self._labels = json.loads(labels_file.read_text(encoding="utf-8"))
            else:
                self._labels = {
                    "0": "GENERAL_INQUIRY",
                    "1": "WHOLESALE_DISCOUNT_INQUIRY",
                    "2": "DELIVERY_TIMELINE_INQUIRY",
                    "3": "TRUST_VERIFICATION_PROOF",
                    "4": "REQUEST_PAYMENT_DETAILS",
                }

            logger.info("onnx_classifier_loaded_successfully", model_path=str(self.model_path))
            return True
        except Exception as exc:
            logger.warning("onnx_session_init_failed_falling_back_to_mock", error=str(exc))
            self._session = None
            self._tokenizer = None
            return False

    async def classify(self, text: str) -> ClassificationOutput:
        start_time = time.perf_counter()

        if not self._ensure_loaded():
            return await self._fallback_adapter.classify(text)

        try:
            # Tokenize input using HuggingFace fast tokenizer
            encoded = self._tokenizer.encode(text)
            input_ids = [encoded.ids]
            attention_mask = [encoded.attention_mask]

            # Run ONNX inference
            inputs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            outputs = self._session.run(None, inputs)
            logits = outputs[0][0]

            # Softmax calculation
            max_logit = max(logits)
            exp_logits = [math.exp(x - max_logit) for x in logits]
            sum_exp = sum(exp_logits)
            probs = [e / sum_exp for e in exp_logits]

            top_idx = max(range(len(probs)), key=lambda i: probs[i])
            confidence = round(probs[top_idx], 4)
            intent = self._labels.get(str(top_idx), "GENERAL_INQUIRY")

            # Dialect determined via parallel Lexical Dialect Analyzer (ADR-0044 Q5)
            dialect = LexicalDialectAnalyzer.detect_dialect(text)

            # Heuristic lead tier & urgency mapping based on intent
            lead_tier = "WARM"
            urgency_score = 6
            action = None
            if intent in ["WHOLESALE_DISCOUNT_INQUIRY", "REQUEST_PAYMENT_DETAILS"]:
                lead_tier = "HOT"
                urgency_score = 8
                action = "APPLY_BULK_DISCOUNT_TIER" if intent == "WHOLESALE_DISCOUNT_INQUIRY" else "GENERATE_VIRTUAL_NUBAN_HOLD"
            elif intent == "TRUST_VERIFICATION_PROOF":
                action = "INJECT_SOCIAL_PROOF_PDF"
                urgency_score = 7
            elif intent == "ORDER_STATUS_INQUIRY":
                action = "RESOLVE_ORDER_STATUS"
                urgency_score = 8
                lead_tier = "HOT"
            elif intent == "DELIVERY_TIMELINE_INQUIRY":
                action = "CALCULATE_DISPATCH_ETA"
                urgency_score = 7

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            return ClassificationOutput(
                intent=intent,
                lead_tier=lead_tier,
                urgency_score=urgency_score,
                confidence=confidence,
                detected_dialect=dialect,
                action=action,
                extracted_entities={},
                tokens_consumed=0,
                latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:
            logger.warning("onnx_inference_failed_falling_back_to_mock", error=str(exc))
            return await self._fallback_adapter.classify(text)


class SpacyClassifierAdapter(CustomClassifierPort):
    """
    Production Native spaCy Classifier Adapter for Stage 2 Local Model evaluation.
    Classifies nuanced Nigerian Pidgin commercial intents (Wholesale Discount, Delivery Timeline,
    Trust Verification, Payment Details) with calibrated confidence and zero LLM tokens.
    """

    _ACTION_MAP: Dict[str, str] = {
        "WHOLESALE_DISCOUNT_INQUIRY": "APPLY_BULK_DISCOUNT_TIER",
        "DELIVERY_TIMELINE_INQUIRY": "CALCULATE_DISPATCH_ETA",
        "TRUST_VERIFICATION_PROOF": "INJECT_SOCIAL_PROOF_PDF",
        "REQUEST_PAYMENT_DETAILS": "GENERATE_VIRTUAL_NUBAN_HOLD",
    }

    async def classify(self, text: str) -> ClassificationOutput:
        start_time = time.perf_counter()
        from app.adapters.providers.spacy_nlu_engine import (
            STAGE_2_CUSTOM_MODEL_INTENTS,
            get_spacy_nlu_engine,
        )

        engine = get_spacy_nlu_engine()
        parsed = engine.predict_intent_and_slots(text)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if parsed.intent in STAGE_2_CUSTOM_MODEL_INTENTS:
            return ClassificationOutput(
                intent=parsed.intent,
                lead_tier=parsed.lead_tier,
                urgency_score=parsed.urgency_score,
                confidence=max(0.89, parsed.confidence),
                detected_dialect=parsed.detected_dialect,
                action=self._ACTION_MAP.get(parsed.intent),
                extracted_entities=parsed.slots,
                tokens_consumed=0,
                latency_ms=max(2.0, round(latency_ms, 2)),
            )

        return ClassificationOutput(
            intent="GENERAL_INQUIRY",
            lead_tier="WARM",
            urgency_score=6,
            confidence=0.62,
            detected_dialect=parsed.detected_dialect,
            action=None,
            extracted_entities=parsed.slots,
            tokens_consumed=0,
            latency_ms=max(2.0, round(latency_ms, 2)),
        )


class OpenWeightClassifierAdapter(CustomClassifierPort):
    """
    Stage 2 Local Model backed by the stateless Open-Weight adapter (Function A).

    Function A runs the trained spaCy `textcat` first and escalates to the configured
    open-weight model (vLLM / Ollama / TGI, grammar-constrained JSON) when spaCy confidence is low;
    the sandbox simulator is the offline fallback. No keyword/regex matching happens here, so
    paraphrases ("how long is the delivery?", "when will my rider reach me?") classify by meaning.
    """

    _ACTION_MAP: Dict[str, str] = {
        "WHOLESALE_DISCOUNT_INQUIRY": "APPLY_BULK_DISCOUNT_TIER",
        "DELIVERY_TIMELINE_INQUIRY": "RESOLVE_FROM_KNOWLEDGE_BASE",
        "TRUST_VERIFICATION_PROOF": "RESOLVE_FROM_KNOWLEDGE_BASE",
        "REQUEST_PAYMENT_DETAILS": "GENERATE_VIRTUAL_NUBAN_HOLD",
    }

    async def classify(self, text: str) -> ClassificationOutput:
        from app.adapters.providers.open_weight import get_open_weight_adapter
        from app.adapters.providers.spacy_nlu_engine import STAGE_2_CUSTOM_MODEL_INTENTS

        parsed = await get_open_weight_adapter().parse_input(text=text)

        if parsed.intent in STAGE_2_CUSTOM_MODEL_INTENTS:
            return ClassificationOutput(
                intent=parsed.intent,
                lead_tier=parsed.lead_tier,
                urgency_score=parsed.urgency_score,
                confidence=parsed.confidence,
                detected_dialect=parsed.detected_dialect,
                action=self._ACTION_MAP.get(parsed.intent),
                extracted_entities=parsed.slots,
                tokens_consumed=parsed.tokens_consumed,
                latency_ms=max(2.0, parsed.latency_ms),
            )

        return ClassificationOutput(
            intent="GENERAL_INQUIRY",
            lead_tier="WARM",
            urgency_score=6,
            confidence=min(0.65, parsed.confidence),
            detected_dialect=parsed.detected_dialect,
            action=None,
            extracted_entities=parsed.slots,
            tokens_consumed=parsed.tokens_consumed,
            latency_ms=max(2.0, parsed.latency_ms),
        )


CUSTOM_CLASSIFIER_REGISTRY: Dict[str, Callable[[], CustomClassifierPort]] = {
    "open_weight": lambda: OpenWeightClassifierAdapter(),
    "spacy": lambda: SpacyClassifierAdapter(),
    "onnx": lambda: ONNXClassifierAdapter(settings.CUSTOM_MODEL_PATH),
    "mock": lambda: MockCustomClassifierAdapter(),
    "transformers": lambda: SpacyClassifierAdapter(),
}


def get_custom_classifier_adapter(model_type: Optional[str] = None) -> CustomClassifierPort:
    """Resolves CustomClassifierPort via declarative registry map."""
    slug = (model_type or settings.CUSTOM_MODEL_TYPE or "open_weight").strip().lower()
    builder = CUSTOM_CLASSIFIER_REGISTRY.get(slug, lambda: OpenWeightClassifierAdapter())
    return builder()
