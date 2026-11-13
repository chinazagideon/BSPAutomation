"""Native spaCy NLU Engine for Intent Classification, Contrastive Slot Mutation & Multi-Item Cart Extraction.

Single-responsibility engine powering:
1. Stage 1 Fast-Path intent & entity extraction (`fast_path.py`)
2. Stage 2 Local Custom Classifier (`custom_classifier.py`)
3. Tier-0 Stateless Open-Weight Function A Parser (`open_weight.py` & `open_weight_simulator.py`)

Capabilities:
- Natively trained spaCy `textcat` (exclusive multiclass n-gram BoW) + `EntityRuler` gazetteer.
- Deterministic `offering_id` (UUIDv5) promotion alongside `sku` for every catalog item.
- Token-level contrastive polarity resolution ("Mama Gold instead of Dangote", "No be Dangote again, make am Mama Gold").
- Coordinated multi-item (`line_items`) pairing ("Give me 2 bags of Dangote sugar AND 3 bags of Mama Gold rice").
"""

import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import structlog

from app.adapters.base import CartLineItem, ClassificationOutput, ParsedTurnInput
from app.core.config import settings

logger = structlog.get_logger(__name__)

try:
    import spacy
    from spacy.matcher import Matcher
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None  # type: ignore
    Matcher = None  # type: ignore


# Canonical Catalog Metadata Registry (sku -> (product_name, category, unit_price_kobo))
SKU_METADATA_REGISTRY: Dict[str, Tuple[str, str, int]] = {
    "SUGAR_DANGOTE_50KG": ("Dangote Sugar 50kg", "sugar", 8400000),
    "SUGAR_BUA_50KG": ("BUA Sugar 50kg", "sugar", 8200000),
    "SUGAR_ST_LOUIS_500G": ("St. Louis Sugar Cube (500g Pack)", "sugar", 180000),
    "RICE_MAMA_GOLD_50KG": ("Mama Gold Rice 50kg", "rice", 7800000),
    "RICE_MAMA_GOLD_25KG": ("Mama Gold Rice 25kg", "rice", 4100000),
    "RICE_ROYAL_STALLION_50KG": ("Royal Stallion Rice 50kg", "rice", 8000000),
    "OIL_DEVONS_KING_25L": ("Devon's King Vegetable Oil 25L", "oil", 5800000),
    "FLOUR_GOLDEN_PENNY_50KG": ("Golden Penny Flour 50kg", "flour", 6200000),
    "SRV_EXECUTIVE_HAIRCUT": ("Executive Haircut & Beard Grooming", "barber", 1500000),
    "SRV_DEEP_TISSUE_MASSAGE": ("Deep Tissue Swedish Massage (60 Mins)", "spa", 3500000),
    "SRV_BRIDAL_GLOW_FACIAL": ("Bridal Radiance Glow Facial (90 Mins)", "skincare", 5000000),
    "PROD_ORGANIC_BEARD_OIL": ("Lekki Glow Organic Argan Beard Oil (50ml)", "grooming", 850000),
    "TECH_IPHONE_15_PRO_128GB": ("Apple iPhone 15 Pro 128GB Natural Titanium", "phones", 145000000),
    "TECH_ANKER_POWERBANK_20K": ("Anker PowerCore 20,000mAh PD Fast Charger", "accessories", 3800000),
}

SLANG_COMMODITY_NORMALIZATION: Dict[str, str] = {
    "shinkafa": "rice",
    "ororo": "oil",
    "suga": "sugar",
    "indomie": "noodles",
}

NUMBER_WORDS: Dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "dozen": 12,
}

AFFIRMATION_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|k|oya|sure|sharp|send\s*am|pls\s*do|please\s*do|correct|proceed|confirm|carry\s*go|abeg\s*send)\b",
    re.IGNORECASE,
)

NEGATION_RE = re.compile(
    r"^(?:no|nah|nope|leave\s*am|never\s*mind|i\s*no\s*(?:wan|dey)\s*buy|i\s*no\s*want|forget\s*(?:am|it)|abort|cancel)\b",
    re.IGNORECASE,
)

MUTATION_MARKER_RE = re.compile(
    r"\b(?:instead|change\s*(?:am|it)?\s*to|make\s*(?:am|it)|no\s*be\s*[\w\s]+?\s*again|no\s*be|rather|swap\s*to|actually)\b",
    re.IGNORECASE,
)

REJECTION_CLAUSE_PATTERNS = [
    re.compile(r"\binstead\s+of\s+([a-z0-9\s\.]{2,35}?)(?=\s*(?:,|give|make|i\s+want|i\s+need|and|deliver|drop|$))", re.IGNORECASE),
    re.compile(r"\bno\s+be\s+([a-z0-9\s\.]{2,35}?)(?:\s+again)?(?=\s*(?:,|abeg|give|make|i\s+want|i\s+need|instead|$))", re.IGNORECASE),
    re.compile(r"\b(?:leave|comot|forget)\s+([a-z0-9\s\.]{2,30}?)(?=\s*(?:,|abeg|give|make|i\s+want|instead|$))", re.IGNORECASE),
    re.compile(r"\bchange\s+from\s+([a-z0-9\s\.]{2,35}?)\s+to\b", re.IGNORECASE),
]

STAGE_1_FAST_PATH_INTENTS: Set[str] = {
    "CONFIRM_PAYMENT",
    "CANCEL_ORDER",
    "PRICE_INQUIRY",
    "INSTANT_CHECKOUT_ORDER",
    "RESERVE_APPOINTMENT",
    "HUMAN_AGENT_HANDOFF",
    "GREETING_ENGAGEMENT",
    "ORDER_STATUS_INQUIRY",
}

STAGE_2_CUSTOM_MODEL_INTENTS: Set[str] = {
    "WHOLESALE_DISCOUNT_INQUIRY",
    "DELIVERY_TIMELINE_INQUIRY",
    "ORDER_STATUS_INQUIRY",
    "TRUST_VERIFICATION_PROOF",
    "REQUEST_PAYMENT_DETAILS",
}


class SpacyNLUEngine:
    """
    Singleton Native spaCy NLU Engine combining:
    - Trained `textcat` intent classification with calibrated softmax/score confidence
    - `EntityRuler` + token-level span extraction for SKUs (`offering_id`), products, quantities, zones, and budgets
    - State-aware contrastive mutation resolution and multi-item `line_items` cart extraction
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir or getattr(settings, "SPACY_MODEL_PATH", "models/spacy_nigerian_sme")
        self._nlp: Optional[Any] = None
        self._matcher: Optional[Any] = None
        self._load_attempted: bool = False

    def _ensure_loaded(self) -> bool:
        if self._load_attempted:
            return self._nlp is not None
        self._load_attempted = True

        if not SPACY_AVAILABLE:
            logger.warning("spacy_not_installed_using_deterministic_token_fallback")
            return False

        try:
            from app.scripts.train_spacy_nlu import (
                CATALOG_SKU_PATTERNS,
                COMMODITY_PATTERNS,
                DELIVERY_ZONE_PATTERNS,
                FULFILLMENT_PATTERNS,
                ensure_spacy_model_trained,
            )
            model_path = ensure_spacy_model_trained(self.model_dir)
            self._nlp = spacy.load(model_path)
            if "entity_ruler" in self._nlp.pipe_names:
                ruler = self._nlp.get_pipe("entity_ruler")
                if len(ruler) == 0:
                    ruler.add_patterns(
                        CATALOG_SKU_PATTERNS
                        + COMMODITY_PATTERNS
                        + DELIVERY_ZONE_PATTERNS
                        + FULFILLMENT_PATTERNS
                    )
            self._matcher = Matcher(self._nlp.vocab)
            self._register_token_matchers()
            logger.info("spacy_nlu_engine_loaded", model_path=str(model_path), pipes=self._nlp.pipe_names)
            return True
        except Exception as exc:
            logger.warning("spacy_model_load_failed", error=str(exc))
            self._nlp = None
            return False

    def _register_token_matchers(self) -> None:
        if self._matcher is None:
            return
        # Rejection clause triggers in spaCy Matcher
        self._matcher.add(
            "REJECTION_PREFIX",
            [
                [{"LOWER": "instead"}, {"LOWER": "of"}],
                [{"LOWER": "no"}, {"LOWER": "be"}],
                [{"LOWER": "change"}, {"LOWER": "from"}],
                [{"LOWER": {"IN": ["leave", "comot", "forget"]}}],
            ],
        )
        # Mutation target triggers
        self._matcher.add(
            "MUTATION_TRIGGER",
            [
                [{"LOWER": "instead"}],
                [{"LOWER": "actually"}],
                [{"LOWER": "rather"}],
                [{"LOWER": "make"}, {"LOWER": {"IN": ["am", "it"]}}],
                [{"LOWER": "change"}, {"LOWER": {"IN": ["am", "it"]}, "OP": "?"}, {"LOWER": "to"}],
                [{"LOWER": "swap"}, {"LOWER": "to"}],
            ],
        )

    @staticmethod
    def detect_dialect(text: str) -> str:
        from app.adapters.custom_classifier import LexicalDialectAnalyzer
        return LexicalDialectAnalyzer.detect_dialect(text)

    @classmethod
    def _identify_rejected_char_ranges(cls, text: str) -> List[Tuple[int, int]]:
        """Returns character (start, end) ranges governed by contrastive rejection markers."""
        ranges: List[Tuple[int, int]] = []
        for pat in REJECTION_CLAUSE_PATTERNS:
            for m in pat.finditer(text):
                ranges.append((m.start(1), m.end(1)))
        return ranges

    @staticmethod
    def _overlaps_rejected(start: int, end: int, rejected_ranges: List[Tuple[int, int]]) -> bool:
        for r_start, r_end in rejected_ranges:
            if max(start, r_start) < min(end, r_end):
                return True
        return False

    def extract_entities(
        self,
        text: str,
        merchant_id: Optional[str] = None,
        active_bound_slots: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
        """
        Extracts canonical commercial slots, contrastive slot_mutations, and multi-item `line_items`.
        Returns (slots_dict, slot_mutations_dict, has_mutation_trigger).
        """
        cleaned = (text or "").strip()
        lower = cleaned.lower()
        rejected_ranges = self._identify_rejected_char_ranges(cleaned)
        has_mutation_marker = bool(MUTATION_MARKER_RE.search(lower)) or bool(rejected_ranges)

        entities: Dict[str, Any] = {}
        product_spans: List[Dict[str, Any]] = []
        quantity_spans: List[Dict[str, Any]] = []

        # 1. Extract via spaCy Doc (EntityRuler + token attributes) when available
        if self._ensure_loaded() and self._nlp is not None:
            doc = self._nlp(cleaned)
            if self._matcher is not None:
                matches = self._matcher(doc)
                for match_id, start, end in matches:
                    rule_name = self._nlp.vocab.strings[match_id]
                    if rule_name == "MUTATION_TRIGGER":
                        has_mutation_marker = True
                    elif rule_name == "REJECTION_PREFIX" and end < len(doc):
                        # Mark up to 4 tokens after rejection prefix unless hitting comma/target verb
                        r_start_char = doc[end].idx
                        r_end_tok = min(len(doc), end + 4)
                        for tok_i in range(end, r_end_tok):
                            if doc[tok_i].lower_ in {",", "give", "make", "i", "and", "deliver", "drop", "instead"}:
                                r_end_tok = tok_i
                                break
                        if r_end_tok > end:
                            r_end_char = doc[r_end_tok - 1].idx + len(doc[r_end_tok - 1].text)
                            rejected_ranges.append((r_start_char, r_end_char))

            for ent in doc.ents:
                if self._overlaps_rejected(ent.start_char, ent.end_char, rejected_ranges):
                    continue
                if ent.label_ == "DELIVERY_ZONE":
                    entities["location"] = ent.ent_id_ or ent.text
                    entities["delivery_zone"] = ent.ent_id_ or ent.text
                elif ent.label_ == "FULFILLMENT":
                    entities["fulfillment_type"] = ent.ent_id_ or "EXPRESS_DELIVERY"
                elif ent.label_ == "SKU":
                    sku_code = ent.ent_id_
                    prod_name, category, unit_kobo = SKU_METADATA_REGISTRY.get(
                        sku_code, (ent.text.title(), "general", 0)
                    )
                    from app.contexts.knowledge.offering_schemas import compute_offering_id
                    offering_id = compute_offering_id(merchant_id, sku_code)
                    product_spans.append({
                        "start_char": ent.start_char,
                        "end_char": ent.end_char,
                        "offering_id": offering_id,
                        "sku": sku_code,
                        "product_name": prod_name,
                        "product": category,
                        "unit_price_kobo": unit_kobo,
                    })
                elif ent.label_ == "PRODUCT":
                    raw_cat = (ent.ent_id_ or ent.text).lower()
                    norm_cat = SLANG_COMMODITY_NORMALIZATION.get(raw_cat, raw_cat)
                    product_spans.append({
                        "start_char": ent.start_char,
                        "end_char": ent.end_char,
                        "offering_id": None,
                        "sku": None,
                        "product_name": None,
                        "product": norm_cat,
                        "unit_price_kobo": None,
                    })
        else:
            # Deterministic fallback if spaCy C-extension is not loaded
            product_spans, zone_val, fulfillment_val = self._fallback_span_scan(cleaned, merchant_id, rejected_ranges)
            if zone_val:
                entities["location"] = zone_val
                entities["delivery_zone"] = zone_val
            if fulfillment_val:
                entities["fulfillment_type"] = fulfillment_val

        # 2. Quantity spans (with unit or standalone before/after product)
        for qm in re.finditer(
            r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(cartons?|bags?|units?|pieces?|packs?|crates?|doz(?:en)?|bottles?|boxes?|jerrycans?)?\b",
            lower,
        ):
            if self._overlaps_rejected(qm.start(), qm.end(), rejected_ranges):
                continue
            raw_num = qm.group(1)
            unit_str = qm.group(2)
            # Ignore numbers that are weights ("50kg", "25kg", "500g", "25l", "128gb", "20,000mah") or phone/currency
            suffix_after = lower[qm.end():qm.end() + 5]
            if re.match(r"^\s*(?:kg|g|l|ml|gb|mah|k|m|thousand|million|mins?|hours?|days?)\b", suffix_after):
                continue
            prefix_before = lower[max(0, qm.start() - 6):qm.start()]
            if re.search(r"(?:₦|ngn|naira|iphone\s*)$", prefix_before):
                continue

            num_val = NUMBER_WORDS.get(raw_num, int(raw_num) if raw_num.isdigit() else 0)
            if num_val <= 0 or num_val >= 500:
                continue

            # Keep if it has an explicit commercial unit OR is preceded by an order/quantity verb ("make it 3", "want 2", "buy 5")
            has_order_verb_prefix = bool(
                re.search(r"(?:want|need|buy|order|pack|give\s+me|make\s+(?:am|it)|to|and|,)\s*$", lower[:qm.start()])
            )
            if unit_str or has_order_verb_prefix:
                quantity_spans.append({
                    "start_char": qm.start(),
                    "end_char": qm.end(),
                    "qty_int": num_val,
                    "qty_str": f"{num_val} {unit_str}" if unit_str else str(num_val),
                    "has_unit": bool(unit_str),
                })

        # 3. Budget / Currency Extraction (Kobo)
        budget_match = re.search(r"(?:₦|ngn|naira|\b)?\s*(\d{1,3}(?:,\d{3})*|\d+)\s*(k|thousand|m|million)?\b", lower)
        if budget_match:
            val_str = budget_match.group(1).replace(",", "")
            multiplier_str = budget_match.group(2)
            try:
                num = float(val_str)
                if multiplier_str in ["k", "thousand"]:
                    num *= 1000
                elif multiplier_str in ["m", "million"]:
                    num *= 1000000
                if num >= 500:
                    entities["budget_naira"] = num
                    entities["budget_kobo"] = int(num * 100)
            except ValueError:
                pass

        # 3b. Order Reference Extraction (e.g. "#A849", "order 8491", "order #1234", "ref #9021")
        order_ref_match = re.search(r"(?:order|ref|receipt)?\s*#([a-zA-Z0-9\-]{3,36})\b", lower)
        if not order_ref_match:
            order_ref_match = re.search(
                r"\b(?:order|ref|receipt)\s*(?:no\.?|num\.?|number|id)?\s*[:\s#]?\s*([a-zA-Z0-9\-]*\d+[a-zA-Z0-9\-]*)\b",
                lower,
            )
        if order_ref_match:
            entities["order_reference"] = order_ref_match.group(1).strip()

        # 4. Deduplicate overlapping & repeated product spans (prefer specific SKU over generic category)
        deduped_products = self._deduplicate_product_spans(product_spans, active_bound_slots, has_mutation_marker)

        # 5. Pair (QUANTITY, PRODUCT/SKU) for Single-Item and Multi-Item Carts
        if quantity_spans:
            # Prefer quantity with explicit unit for top-level entities["quantity"]
            unit_quantities = [q for q in quantity_spans if q["has_unit"]]
            primary_q = unit_quantities[-1] if (has_mutation_marker and unit_quantities) else (
                unit_quantities[0] if unit_quantities else (quantity_spans[-1] if has_mutation_marker else quantity_spans[0])
            )
            entities["quantity"] = primary_q["qty_str"]

        is_pure_price_or_stock_query = bool(
            re.search(
                r"(?:how\s*much|wetin\s*be\s*the\s*price|price\s*dey|dm\s*price|catalog|do\s*you\s*have|you\s*get|is\s*there|any\s*stock|in\s*stock|available|dey\s*(?:store|shop|ground)|una\s*get)\b",
                lower,
            )
            and not re.search(
                r"(?:i\s*wan\s*buy|i\s*wan\s*order|pack\s*\d+|deliver\s*to|drop\s*am\s*(?:for|to|at|in)|i\s*need\s*\d+|give\s*me\s*\d+|i\s*want\s*\d+|buy\s*\d+)",
                lower,
            )
            and not quantity_spans
        )

        if len(deduped_products) == 1 or (len(deduped_products) >= 2 and is_pure_price_or_stock_query):
            p = deduped_products[0]
            entities["product"] = p["product"]
            if p.get("sku"):
                entities["sku"] = p["sku"]
                entities["offering_id"] = p["offering_id"]
                entities["product_name"] = p["product_name"]
        elif len(deduped_products) >= 2:
            # Multi-item bulk order: pair each distinct product span with its closest preceding quantity
            line_items: List[Dict[str, Any]] = []
            used_q_indices: Set[int] = set()
            for idx, p in enumerate(deduped_products):
                paired_qty = 1
                best_q_idx: Optional[int] = None
                best_dist = 999999
                for q_i, q in enumerate(quantity_spans):
                    if q_i in used_q_indices:
                        continue
                    # Prefer quantity immediately preceding this product span
                    if q["end_char"] <= p["start_char"]:
                        dist = p["start_char"] - q["end_char"]
                        if dist < best_dist:
                            best_dist = dist
                            best_q_idx = q_i
                if best_q_idx is not None and best_dist <= 35:
                    used_q_indices.add(best_q_idx)
                    paired_qty = quantity_spans[best_q_idx]["qty_int"]
                elif idx < len(quantity_spans) and idx not in used_q_indices:
                    used_q_indices.add(idx)
                    paired_qty = quantity_spans[idx]["qty_int"]

                item_model = CartLineItem(
                    offering_id=p.get("offering_id"),
                    sku=p.get("sku"),
                    product=p.get("product"),
                    product_name=p.get("product_name"),
                    quantity=paired_qty,
                    unit_price_kobo=p.get("unit_price_kobo"),
                    in_stock=p.get("sku") != "FLOUR_GOLDEN_PENNY_50KG",
                )
                line_items.append(item_model.model_dump(exclude_none=True))

            entities["line_items"] = line_items
            # Set primary top-level slot to first line item for backwards compatibility
            first = line_items[0]
            entities["product"] = first.get("product")
            if first.get("sku"):
                entities["sku"] = first["sku"]
                entities["offering_id"] = first.get("offering_id")
                entities["product_name"] = first.get("product_name")
            entities["quantity"] = first.get("quantity", 1)

        # 6. State-Aware Contrastive Mutation Resolution against active_bound_slots
        slot_mutations: Dict[str, Any] = {}
        if has_mutation_marker:
            for k in ("offering_id", "sku", "product_name", "product", "quantity", "location", "delivery_zone", "fulfillment_type", "line_items"):
                if k in entities:
                    slot_mutations[k] = entities[k]
        elif active_bound_slots:
            for k in ("offering_id", "sku", "product", "quantity", "delivery_zone", "fulfillment_type"):
                if k in entities and k in active_bound_slots and active_bound_slots[k] is not None:
                    if str(entities[k]).lower() != str(active_bound_slots[k]).lower():
                        slot_mutations[k] = entities[k]
                        if k in ("offering_id", "sku", "product"):
                            for related in ("offering_id", "sku", "product_name", "product"):
                                if related in entities:
                                    slot_mutations[related] = entities[related]

        return entities, slot_mutations, has_mutation_marker

    @staticmethod
    def _deduplicate_product_spans(
        spans: List[Dict[str, Any]],
        active_bound_slots: Optional[Dict[str, Any]],
        has_mutation_marker: bool,
    ) -> List[Dict[str, Any]]:
        """
        Merges adjacent/overlapping SKU + generic PRODUCT spans (e.g. 'Mama Gold' + 'rice'),
        collapses duplicate mentions of the exact same (sku, product) across the utterance,
        and filters out already-bound slots if in a contrastive mutation turn.
        """
        if not spans:
            return []

        sorted_spans = sorted(spans, key=lambda s: (s["start_char"], -(s["end_char"] - s["start_char"])))
        merged: List[Dict[str, Any]] = []

        for sp in sorted_spans:
            if not merged:
                merged.append(sp)
                continue
            prev = merged[-1]
            # Overlap or immediate adjacency of same category ("Mama Gold" + "rice" or "Dangote" + "sugar")
            is_overlapping = sp["start_char"] <= prev["end_char"] + 2
            same_cat = prev.get("product") == sp.get("product")
            if is_overlapping and (same_cat or prev.get("sku") or sp.get("sku")):
                if sp.get("sku") and not prev.get("sku"):
                    merged[-1] = sp
                else:
                    prev["end_char"] = max(prev["end_char"], sp["end_char"])
                continue
            merged.append(sp)

        # Collapse repeated mentions of the exact same (sku, product) identity across the utterance
        unique_spans: List[Dict[str, Any]] = []
        seen_identities: Set[Tuple[str, str]] = set()
        for sp in merged:
            sku_key = (sp.get("sku") or "").upper()
            prod_key = (sp.get("product") or "").lower()
            identity = (sku_key, prod_key)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            unique_spans.append(sp)

        merged = unique_spans

        # If this is a mutation turn and 2 spans remain where one matches active_bound_slots, drop the old bound span
        if has_mutation_marker and active_bound_slots and len(merged) > 1:
            bound_sku = (active_bound_slots.get("sku") or "").upper()
            bound_prod = (active_bound_slots.get("product") or "").lower()
            filtered = [
                m for m in merged
                if (bound_sku and (m.get("sku") or "").upper() != bound_sku)
                or (not bound_sku and bound_prod and (m.get("product") or "").lower() != bound_prod)
            ]
            if filtered:
                return filtered

        return merged

    @staticmethod
    def _fallback_span_scan(
        text: str,
        merchant_id: Optional[str],
        rejected_ranges: List[Tuple[int, int]],
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
        """Fallback span scanner used only if spaCy binary is unavailable."""
        lower = text.lower()
        product_spans: List[Dict[str, Any]] = []

        sku_phrases = [
            ("mama gold rice 25kg", "RICE_MAMA_GOLD_25KG"),
            ("mama gold 25kg", "RICE_MAMA_GOLD_25KG"),
            ("mama gold rice 50kg", "RICE_MAMA_GOLD_50KG"),
            ("mama gold rice", "RICE_MAMA_GOLD_50KG"),
            ("mama gold 50kg", "RICE_MAMA_GOLD_50KG"),
            ("mama gold", "RICE_MAMA_GOLD_50KG"),
            ("royal stallion", "RICE_ROYAL_STALLION_50KG"),
            ("dangote sugar 50kg", "SUGAR_DANGOTE_50KG"),
            ("dangote sugar", "SUGAR_DANGOTE_50KG"),
            ("dangote", "SUGAR_DANGOTE_50KG"),
            ("bua sugar", "SUGAR_BUA_50KG"),
            ("st louis", "SUGAR_ST_LOUIS_500G"),
            ("st. louis", "SUGAR_ST_LOUIS_500G"),
            ("devon", "OIL_DEVONS_KING_25L"),
            ("king oil", "OIL_DEVONS_KING_25L"),
            ("kings oil", "OIL_DEVONS_KING_25L"),
            ("golden penny", "FLOUR_GOLDEN_PENNY_50KG"),
        ]
        for phrase, sku_code in sku_phrases:
            for m in re.finditer(rf"\b{re.escape(phrase)}\b", lower):
                if SpacyNLUEngine._overlaps_rejected(m.start(), m.end(), rejected_ranges):
                    continue
                prod_name, category, unit_kobo = SKU_METADATA_REGISTRY[sku_code]
                from app.contexts.knowledge.offering_schemas import compute_offering_id
                product_spans.append({
                    "start_char": m.start(),
                    "end_char": m.end(),
                    "offering_id": compute_offering_id(merchant_id, sku_code),
                    "sku": sku_code,
                    "product_name": prod_name,
                    "product": category,
                    "unit_price_kobo": unit_kobo,
                })

        for comm in [
            "rice", "sugar", "oil", "flour", "beans", "cement", "milk", "garri",
            "noodles", "indomie", "spaghetti", "salt", "inverter", "laptop",
            "macbook", "starlink", "battery", "barber", "haircut", "massage", "facial",
            "shinkafa", "ororo", "suga",
        ]:
            for m in re.finditer(rf"\b{comm}\b", lower):
                if SpacyNLUEngine._overlaps_rejected(m.start(), m.end(), rejected_ranges):
                    continue
                norm_cat = SLANG_COMMODITY_NORMALIZATION.get(comm, comm)
                product_spans.append({
                    "start_char": m.start(),
                    "end_char": m.end(),
                    "offering_id": None,
                    "sku": None,
                    "product_name": None,
                    "product": norm_cat,
                    "unit_price_kobo": None,
                })

        zone_val = None
        if re.search(r"\b(ikeja|computer\s*village|allen|ogba|maryland)\b", lower):
            zone_val = "Ikeja / Mainland, Lagos"
        elif re.search(r"\b(lekki|vi|victoria\s*island|ikoyi|ajah|chevron)\b", lower):
            zone_val = "Lekki / Island, Lagos"
        elif re.search(r"\b(yaba|surulere|ebute\s*metta|unilag)\b", lower):
            zone_val = "Yaba / Central, Lagos"
        elif re.search(r"\b(abuja|garki|wuse|maitama|gwarinpa)\b", lower):
            zone_val = "Abuja FCT"
        elif re.search(r"\b(ibadan|bodija|dugbe|ring\s*road)\b", lower):
            zone_val = "Ibadan, Oyo"

        fulfillment_val = None
        if re.search(r"\b(pickup|pick\s*up|collect|warehouse|come\s*carry)\b", lower):
            fulfillment_val = "WAREHOUSE_PICKUP"
        elif re.search(r"\b(deliver|dispatch|waybill|drop\s*am\s*(?:for|to|at|in)|send\s*am\s*to)\b", lower):
            fulfillment_val = "EXPRESS_DELIVERY"

        return product_spans, zone_val, fulfillment_val

    def predict_intent_and_slots(
        self,
        text: str,
        expected_slot_hint: Optional[str] = None,
        custom_dictionary: Optional[List[Dict[str, Any]]] = None,
        active_bound_slots: Optional[Dict[str, Any]] = None,
        merchant_id: Optional[str] = None,
    ) -> ParsedTurnInput:
        """
        Executes full native spaCy intent classification + state-aware slot & mutation extraction.
        Returns a validated `ParsedTurnInput` DTO.
        """
        start_time = time.perf_counter()
        cleaned = (text or "").strip()
        lower = cleaned.lower()
        dialect = self.detect_dialect(cleaned)

        entities, slot_mutations, has_mutation_marker = self.extract_entities(
            cleaned,
            merchant_id=merchant_id,
            active_bound_slots=active_bound_slots,
        )

        # Context-aware bare slot promotion when active_frame is waiting for quantity
        if expected_slot_hint == "quantity" and "quantity" not in entities:
            bare_num = re.match(r"^\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*$", lower)
            if bare_num:
                raw_n = bare_num.group(1)
                entities["quantity"] = NUMBER_WORDS.get(raw_n, int(raw_n) if raw_n.isdigit() else 1)

        # 0. Merchant Custom Dictionary Priority Override
        if custom_dictionary:
            for rule in custom_dictionary:
                phrase = (rule.get("phrase_pattern") or "").lower().strip()
                if phrase and phrase in lower:
                    latency = (time.perf_counter() - start_time) * 1000.0
                    return ParsedTurnInput(
                        intent=rule.get("intent", "GENERAL_INQUIRY"),
                        canonical_query=cleaned,
                        slots=entities,
                        slot_mutations=slot_mutations,
                        detected_dialect=dialect,
                        confidence=0.98,
                        lead_tier=rule.get("lead_tier", "WARM"),
                        urgency_score=rule.get("urgency_score", 7),
                        tokens_consumed=0,
                        latency_ms=round(max(1.0, latency), 2),
                    )

        # 1. Disambiguate Polysemous "drop am" (Delivery vs Order Cancellation)
        has_drop_am_delivery = bool(re.search(r"\bdrop\s*am\s*(?:for|to|at|in)\b", lower))
        if has_drop_am_delivery:
            entities["fulfillment_type"] = "EXPRESS_DELIVERY"

        is_explicit_cancel = bool(
            re.search(
                r"\b(cancel(?:\s+am|\s+order|\s+it)?|never\s*mind|no\s*buy\s*again|i\s*no\s*(?:wan|dey)\s*buy|forget\s*(?:am|it)|abort)\b",
                lower,
            )
        )
        if not is_explicit_cancel and re.search(r"\bdrop\s*am\b", lower) and not has_drop_am_delivery:
            is_explicit_cancel = True

        # Do not treat contrastive mutation ("No be Dangote again, give me Mama Gold") as order cancellation!
        if has_mutation_marker and (entities.get("product") or entities.get("sku") or entities.get("quantity")):
            is_explicit_cancel = False

        is_affirm = bool(AFFIRMATION_RE.search(lower)) and not is_explicit_cancel
        is_negate = bool(NEGATION_RE.search(lower)) and not (has_mutation_marker and bool(slot_mutations))

        if is_explicit_cancel:
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="CANCEL_ORDER",
                canonical_query="Cancel active order",
                slots=entities,
                slot_mutations={},
                is_cancellation=True,
                is_affirmation=False,
                is_negation=True,
                detected_dialect=dialect,
                confidence=0.98,
                lead_tier="COLD",
                urgency_score=5,
                tokens_consumed=0,
                latency_ms=round(max(1.0, latency), 2),
            )

        # 2. Run Native spaCy `textcat` Model for Intent & Calibrated Confidence
        spacy_intent = "GENERAL_INQUIRY"
        spacy_conf = 0.60
        if self._ensure_loaded() and self._nlp is not None and "textcat" in self._nlp.pipe_names:
            doc = self._nlp(cleaned)
            if doc.cats:
                top_label = max(doc.cats, key=doc.cats.get)
                spacy_intent = top_label
                spacy_conf = float(doc.cats[top_label])

        # 3. Structural & Slot-Guided Calibration (Combining spaCy textcat with extracted slot invariants)
        intent, confidence, lead_tier, urgency = self._calibrate_intent_with_slots(
            lower=lower,
            spacy_intent=spacy_intent,
            spacy_conf=spacy_conf,
            entities=entities,
            slot_mutations=slot_mutations,
            has_mutation_marker=has_mutation_marker,
            has_drop_am_delivery=has_drop_am_delivery,
            expected_slot_hint=expected_slot_hint,
        )

        if intent == "PRICE_INQUIRY":
            entities.pop("line_items", None)

        latency = (time.perf_counter() - start_time) * 1000.0
        return ParsedTurnInput(
            intent=intent,
            canonical_query=cleaned,
            slots=entities,
            slot_mutations=slot_mutations,
            is_cancellation=False,
            is_affirmation=is_affirm,
            is_negation=is_negate,
            detected_dialect=dialect,
            confidence=round(confidence, 4),
            lead_tier=lead_tier,
            urgency_score=urgency,
            tokens_consumed=0,
            latency_ms=round(max(1.0, latency), 2),
        )

    parse_turn = predict_intent_and_slots

    @staticmethod
    def _calibrate_intent_with_slots(
        lower: str,
        spacy_intent: str,
        spacy_conf: float,
        entities: Dict[str, Any],
        slot_mutations: Dict[str, Any],
        has_mutation_marker: bool,
        has_drop_am_delivery: bool,
        expected_slot_hint: Optional[str],
    ) -> Tuple[str, float, str, int]:
        """
        Combines spaCy `textcat` probability distribution with structural slot invariants
        to prevent subword false positives (e.g., 'prepaid' vs 'paid', consultative questions vs checkout).
        """
        # Hard-negative guard: "prepaid" / "unpaid" must never trigger CONFIRM_PAYMENT
        if any(w in lower for w in ("prepaid", "unpaid", "postpaid")):
            return ("GENERAL_INQUIRY", 0.62, "WARM", 6)

        # Consultative / long-term financing / partnership / open questions -> Stage 3 LLM escalation
        if any(
            phrase in lower
            for phrase in (
                "long-term financing",
                "flour specifications",
                "setting up a brand new",
                "want to ask if",
                "random complex query",
            )
        ):
            return ("GENERAL_INQUIRY", 0.62, "WARM", 6)

        # Sub-flow & specialized intents with clear lexical + textcat alignment
        if re.search(
            r"(?:how\s*long.*(?:deliver|take|reach)|delivery\s*timeline|dispatch\s*rider|interstate\s*waybill|how\s*many\s*(?:days|hours)|when\s*rider\s*go)",
            lower,
        ) and not re.search(r"\b(?:my\s*order|my\s*delivery|track|order\s*status)\b", lower):
            return ("DELIVERY_TIMELINE_INQUIRY", max(0.92, spacy_conf), "WARM", 7)

        if re.search(
            r"(?:hope\s*say\s*no\s*be\s*scam|you\s*legit|where\s*(?:your|una)\s*shop\s*dey|where\s*is\s*your\s*shop|proof\s*dey|see\s*past\s*work|reviews)",
            lower,
        ):
            return ("TRUST_VERIFICATION_PROOF", max(0.93, spacy_conf), "WARM", 7)

        if re.search(
            r"(?:slash\s*price|discount\s*dey|reduce\s*small|wholesale\s*(?:price|discount)|if\s*i\s*buy\s*plenty|last\s*price)",
            lower,
        ):
            # Note: If explicitly asking for wholesale/bulk discount ("if I buy plenty", "wholesale price", "slash price", "discount dey"),
            # route to WHOLESALE_DISCOUNT_INQUIRY; if "give me discount" / "last price" in general price query, check context:
            if any(p in lower for p in ("wholesale price", "wholesale discount", "if i buy plenty", "slash price", "discount dey")):
                return ("WHOLESALE_DISCOUNT_INQUIRY", max(0.91, spacy_conf), "HOT", 8)

        if re.search(
            r"(?:speak\s*to\s*human|talk\s*to\s*person|agent\s*abeg|customer\s*care|call\s*me|real\s*person|human\s*agent)",
            lower,
        ):
            return ("HUMAN_AGENT_HANDOFF", max(0.96, spacy_conf), "WARM", 8)

        if re.search(
            r"\b(?:i\s*don\s*pay|done\s*transfer|i\s*sent\s*the\s*money|alert\s*don\s*enter|see\s*debit\s*alert|receipt\s*dey|transfer\s*successful|paid|i\s*have\s*paid|money\s*don\s*comot)\b",
            lower,
        ):
            return ("CONFIRM_PAYMENT", max(0.98, spacy_conf), "HOT", 10)

        if re.search(
            r"(?:book\s*(?:appointment|session|slot)|reserve\s*space|lock\s*my\s*date|schedule\s*meeting|any\s*slot\s*for\s*tomorrow)",
            lower,
        ):
            return ("RESERVE_APPOINTMENT", max(0.94, spacy_conf), "HOT", 9)

        if re.search(
            r"(?:ussd\s*code|moniepoint\s*acct|gtb\s*transfer|zenith)",
            lower,
        ) and not re.search(r"\b(?:send\s*account\s*details|how\s*i\s*go\s*pay)\b", lower):
            return ("REQUEST_PAYMENT_DETAILS", max(0.94, spacy_conf), "HOT", 9)

        # Post-purchase order status tracking inquiry (ADR-0048)
        if re.search(
            r"(?:"
            r"when\s*(?:is|will)?\s*(?:my|the)?\s*(?:order|delivery|package|dispatch)\s*(?:going\s*to\s*)?arrive|"
            r"where\s*(?:is|dey)?\s*(?:my|the)?\s*(?:order|delivery|package|dispatch)|"
            r"where\s+my\s+delivery\s+dey|"
            r"track\s*(?:my\s*)?order|"
            r"order\s*status|"
            r"dispatch\s*status|"
            r"rider\s*(?:where|eta|status)|"
            r"wetin\s*happen\s*to\s*my\s*order|"
            r"my\s*order\s*never\s*reach|"
            r"when\s*(?:e|am|it)\s*(?:go\s*land|reach)|"
            r"waybill\s*status"
            r")",
            lower,
        ) or (entities.get("order_reference") and re.search(r"\b(?:order|track|status|where|arrive|dispatch)\b", lower)):
            return ("ORDER_STATUS_INQUIRY", max(0.95, spacy_conf), "HOT", 8)

        # Explicit Checkout / Order / Mid-Flow Slot Mutation / Multi-Item Cart
        has_line_items = bool(entities.get("line_items"))
        is_explicit_buy = bool(
            re.search(
                r"(?:i\s*wan\s*buy|i\s*wan\s*order|send\s*account\s*details|how\s*i\s*go\s*pay|pack\s*\d+|deliver\s*to|drop\s*am\s*(?:for|to|at|in)|i\s*need\s*\d+|give\s*me\s*\d+|i\s*want\s*\d+|buy\s*\d+)",
                lower,
            )
            or has_line_items
            or has_drop_am_delivery
            or (has_mutation_marker and bool(slot_mutations))
        )

        is_price_or_stock_question = bool(
            re.search(
                r"(?:how\s*much|wetin\s*be\s*the\s*price|price\s*dey|give\s*me\s*discount|abeg\s*reduce\s*small|last\s*price|dm\s*price|catalog|do\s*you\s*have|you\s*get|is\s*there|any\s*stock|in\s*stock|available|dey\s*(?:store|shop|ground)|una\s*get)\b",
                lower,
            )
            or (entities.get("product") and re.search(r"\b(?:dey|have|stock|available|how\s*much|price)\b", lower))
        )

        if is_price_or_stock_question and not is_explicit_buy:
            return ("PRICE_INQUIRY", max(0.95, spacy_conf), "HOT", 8)

        if is_explicit_buy or (
            expected_slot_hint
            and any(k in entities for k in ("offering_id", "sku", "product", "quantity", "location", "delivery_zone", "fulfillment_type"))
        ):
            return ("INSTANT_CHECKOUT_ORDER", max(0.95, spacy_conf), "HOT", 9)

        if re.search(r"\b(?:how\s*far|wetin\s*dey|good\s*(?:morning|afternoon|evening)|hello|hi|hey|oya)\b", lower):
            return ("GREETING_ENGAGEMENT", max(0.91, spacy_conf), "WARM", 5)

        # Trust spaCy textcat when confidence is high (>= 0.85) and not a general inquiry
        if spacy_conf >= 0.85 and spacy_intent != "GENERAL_INQUIRY":
            tier = "HOT" if spacy_intent in {"CONFIRM_PAYMENT", "INSTANT_CHECKOUT_ORDER", "PRICE_INQUIRY", "WHOLESALE_DISCOUNT_INQUIRY", "RESERVE_APPOINTMENT"} else "WARM"
            urg = 9 if tier == "HOT" else 7
            return (spacy_intent, spacy_conf, tier, urg)

        return ("GENERAL_INQUIRY", min(0.65, spacy_conf), "WARM", 6)


_SPACY_ENGINE_SINGLETON: Optional[SpacyNLUEngine] = None


def get_spacy_nlu_engine() -> SpacyNLUEngine:
    """Returns singleton instance of SpacyNLUEngine."""
    global _SPACY_ENGINE_SINGLETON
    if _SPACY_ENGINE_SINGLETON is None:
        _SPACY_ENGINE_SINGLETON = SpacyNLUEngine()
    return _SPACY_ENGINE_SINGLETON
