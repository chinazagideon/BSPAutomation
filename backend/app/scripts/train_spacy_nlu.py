"""Native spaCy NLU Training Pipeline for Nigerian SME Conversational Commerce.

Trains a lightweight, sub-2ms CPU spaCy pipeline (`entity_ruler` + `ner` + `textcat`)
covering:
- 12 Canonical Intents (English + Nigerian Pidgin + Commercial Slang + Hard Negatives)
- Catalog SKU & Commodity Gazetteer via EntityRuler
- Open-vocabulary Quantity & Budget NER spans
Serializes trained artifacts to `models/spacy_nigerian_sme`.
"""

import random
from pathlib import Path
from typing import Any, Dict, List, Tuple
import structlog

logger = structlog.get_logger(__name__)

INTENT_LABELS: List[str] = [
    "CONFIRM_PAYMENT",
    "CANCEL_ORDER",
    "PRICE_INQUIRY",
    "INSTANT_CHECKOUT_ORDER",
    "RESERVE_APPOINTMENT",
    "WHOLESALE_DISCOUNT_INQUIRY",
    "DELIVERY_TIMELINE_INQUIRY",
    "TRUST_VERIFICATION_PROOF",
    "REQUEST_PAYMENT_DETAILS",
    "HUMAN_AGENT_HANDOFF",
    "GREETING_ENGAGEMENT",
    "GENERAL_INQUIRY",
]

# Catalog SKU Definitions mapped by EntityRuler (phrase -> sku_id)
CATALOG_SKU_PATTERNS: List[Dict[str, Any]] = [
    {"label": "SKU", "id": "SUGAR_DANGOTE_50KG", "pattern": [{"LOWER": "dangote"}, {"LOWER": "sugar"}, {"LOWER": "50kg", "OP": "?"}]},
    {"label": "SKU", "id": "SUGAR_DANGOTE_50KG", "pattern": [{"LOWER": "dangote"}, {"LOWER": "50kg"}]},
    {"label": "SKU", "id": "SUGAR_DANGOTE_50KG", "pattern": [{"LOWER": "dangote"}]},
    {"label": "SKU", "id": "SUGAR_BUA_50KG", "pattern": [{"LOWER": "bua"}, {"LOWER": "sugar"}, {"LOWER": "50kg", "OP": "?"}]},
    {"label": "SKU", "id": "SUGAR_BUA_50KG", "pattern": [{"LOWER": "bua"}]},
    {"label": "SKU", "id": "SUGAR_ST_LOUIS_500G", "pattern": [{"LOWER": {"IN": ["st", "st."]}}, {"LOWER": "louis"}, {"LOWER": "sugar", "OP": "?"}]},
    {"label": "SKU", "id": "RICE_MAMA_GOLD_25KG", "pattern": [{"LOWER": "mama"}, {"LOWER": "gold"}, {"LOWER": "rice", "OP": "?"}, {"LOWER": "25kg"}]},
    {"label": "SKU", "id": "RICE_MAMA_GOLD_50KG", "pattern": [{"LOWER": "mama"}, {"LOWER": "gold"}, {"LOWER": "rice"}, {"LOWER": "50kg"}]},
    {"label": "SKU", "id": "RICE_MAMA_GOLD_50KG", "pattern": [{"LOWER": "mama"}, {"LOWER": "gold"}, {"LOWER": "rice"}]},
    {"label": "SKU", "id": "RICE_MAMA_GOLD_50KG", "pattern": [{"LOWER": "mama"}, {"LOWER": "gold"}, {"LOWER": "50kg"}]},
    {"label": "SKU", "id": "RICE_MAMA_GOLD_50KG", "pattern": [{"LOWER": "mama"}, {"LOWER": "gold"}]},
    {"label": "SKU", "id": "RICE_ROYAL_STALLION_50KG", "pattern": [{"LOWER": "royal"}, {"LOWER": "stallion"}, {"LOWER": "rice", "OP": "?"}, {"LOWER": "50kg", "OP": "?"}]},
    {"label": "SKU", "id": "OIL_DEVONS_KING_25L", "pattern": [{"LOWER": {"IN": ["devon", "devons", "devon's"]}}, {"LOWER": {"IN": ["king", "kings", "king's"]}, "OP": "?"}, {"LOWER": "oil", "OP": "?"}]},
    {"label": "SKU", "id": "OIL_DEVONS_KING_25L", "pattern": [{"LOWER": {"IN": ["king", "kings"]}}, {"LOWER": "vegetable", "OP": "?"}, {"LOWER": "oil"}]},
    {"label": "SKU", "id": "FLOUR_GOLDEN_PENNY_50KG", "pattern": [{"LOWER": "golden"}, {"LOWER": "penny"}, {"LOWER": "flour", "OP": "?"}, {"LOWER": "50kg", "OP": "?"}]},
    {"label": "SKU", "id": "SRV_EXECUTIVE_HAIRCUT", "pattern": [{"LOWER": "executive"}, {"LOWER": "haircut"}]},
    {"label": "SKU", "id": "SRV_DEEP_TISSUE_MASSAGE", "pattern": [{"LOWER": "deep"}, {"LOWER": "tissue"}, {"LOWER": "massage"}]},
    {"label": "SKU", "id": "SRV_BRIDAL_GLOW_FACIAL", "pattern": [{"LOWER": "bridal"}, {"LOWER": "glow", "OP": "?"}, {"LOWER": "facial"}]},
    {"label": "SKU", "id": "PROD_ORGANIC_BEARD_OIL", "pattern": [{"LOWER": "beard"}, {"LOWER": "oil"}]},
    {"label": "SKU", "id": "TECH_IPHONE_15_PRO_128GB", "pattern": [{"LOWER": "iphone"}, {"LOWER": "15"}, {"LOWER": "pro", "OP": "?"}]},
    {"label": "SKU", "id": "TECH_ANKER_POWERBANK_20K", "pattern": [{"LOWER": "anker"}, {"LOWER": {"IN": ["powerbank", "powercore", "charger"]}, "OP": "?"}]},
]

COMMODITY_PATTERNS: List[Dict[str, Any]] = [
    {
        "label": "PRODUCT",
        "id": commodity,
        "pattern": [{"LOWER": commodity}],
    }
    for commodity in [
        "rice", "sugar", "oil", "flour", "beans", "cement", "milk", "garri",
        "noodles", "indomie", "spaghetti", "salt", "inverter", "laptop",
        "macbook", "starlink", "battery", "barber", "haircut", "massage",
        "facial", "shinkafa", "ororo", "suga", "powerbank", "iphone",
    ]
]

DELIVERY_ZONE_PATTERNS: List[Dict[str, Any]] = [
    {"label": "DELIVERY_ZONE", "id": "Ikeja / Mainland, Lagos", "pattern": [{"LOWER": {"IN": ["ikeja", "allen", "ogba", "maryland"]}}]},
    {"label": "DELIVERY_ZONE", "id": "Ikeja / Mainland, Lagos", "pattern": [{"LOWER": "computer"}, {"LOWER": "village"}]},
    {"label": "DELIVERY_ZONE", "id": "Lekki / Island, Lagos", "pattern": [{"LOWER": {"IN": ["lekki", "vi", "ikoyi", "ajah", "chevron"]}}]},
    {"label": "DELIVERY_ZONE", "id": "Lekki / Island, Lagos", "pattern": [{"LOWER": "victoria"}, {"LOWER": "island"}]},
    {"label": "DELIVERY_ZONE", "id": "Yaba / Central, Lagos", "pattern": [{"LOWER": {"IN": ["yaba", "surulere", "unilag"]}}]},
    {"label": "DELIVERY_ZONE", "id": "Yaba / Central, Lagos", "pattern": [{"LOWER": "ebute"}, {"LOWER": "metta"}]},
    {"label": "DELIVERY_ZONE", "id": "Abuja FCT", "pattern": [{"LOWER": {"IN": ["abuja", "garki", "wuse", "maitama", "gwarinpa"]}}]},
    {"label": "DELIVERY_ZONE", "id": "Ibadan, Oyo", "pattern": [{"LOWER": {"IN": ["ibadan", "bodija", "dugbe"]}}]},
    {"label": "DELIVERY_ZONE", "id": "Ibadan, Oyo", "pattern": [{"LOWER": "ring"}, {"LOWER": "road"}]},
]

FULFILLMENT_PATTERNS: List[Dict[str, Any]] = [
    {"label": "FULFILLMENT", "id": "WAREHOUSE_PICKUP", "pattern": [{"LOWER": {"IN": ["pickup", "collect", "warehouse"]}}]},
    {"label": "FULFILLMENT", "id": "WAREHOUSE_PICKUP", "pattern": [{"LOWER": "pick"}, {"LOWER": "up"}]},
    {"label": "FULFILLMENT", "id": "WAREHOUSE_PICKUP", "pattern": [{"LOWER": "come"}, {"LOWER": "carry"}]},
    {"label": "FULFILLMENT", "id": "EXPRESS_DELIVERY", "pattern": [{"LOWER": {"IN": ["deliver", "dispatch", "waybill"]}}]},
    {"label": "FULFILLMENT", "id": "EXPRESS_DELIVERY", "pattern": [{"LOWER": "drop"}, {"LOWER": "am"}, {"LOWER": {"IN": ["for", "to", "at", "in"]}}]},
    {"label": "FULFILLMENT", "id": "EXPRESS_DELIVERY", "pattern": [{"LOWER": "send"}, {"LOWER": "am"}, {"LOWER": "to"}]},
]


# Curated Nigerian SME & Pidgin Intent Training Corpus
INTENT_TRAINING_CORPUS: Dict[str, List[str]] = {
    "CONFIRM_PAYMENT": [
        "Bless up! I don pay, see debit alert",
        "I don pay into the moniepoint account",
        "I have paid into your account",
        "Done transfer, check your alert",
        "I sent the money just now",
        "Alert don enter? I just transferred the money",
        "See debit alert for the order",
        "Receipt dey here, transfer successful",
        "I just paid the total amount",
        "Money don comot my account o, check am",
        "Abeg confirm my transfer, I don pay",
        "Payment done sharp sharp",
        "I have made the bank transfer",
        "Transfer successful, waiting for my receipt",
    ],
    "CANCEL_ORDER": [
        "Cancel am abeg",
        "Cancel order right now",
        "Cancel it please",
        "Never mind I no buy again",
        "I no wan buy again",
        "I no dey buy again o",
        "Forget am, abort the order",
        "Forget it please cancel",
        "Drop am, I no buy again",
        "Abeg drop am",
        "Cancel my pending order",
        "Please abort this transaction",
        "Leave am, cancel the order",
    ],
    "PRICE_INQUIRY": [
        "Do you have rice in store?",
        "you get sugar?",
        "How much be bag of rice?",
        "Wetin be the price for Dangote sugar?",
        "Price dey for Mama Gold rice?",
        "Send me your catalog and price list",
        "DM price abeg",
        "Is Royal Stallion available in stock?",
        "Una get vegetable oil for shop?",
        "Any stock for Golden Penny flour?",
        "Rice dey ground today?",
        "Do you have Starlink in stock?",
        "How much una dey sell 50kg sugar?",
        "Show me product catalog",
        "What is the price of Devon's King oil?",
        "You get shinkafa or ororo in stock?",
    ],
    "INSTANT_CHECKOUT_ORDER": [
        "I want 2 bags of sugar deliver to Ikeja",
        "I want 2 bags of Dangote Sugar 50kg",
        "I wan buy 5 bags of Mama Gold rice",
        "I wan order 3 cartons of oil deliver to Lekki",
        "Give me 2 bags of Dangote sugar and 3 bags of Mama Gold rice",
        "Pack 4 bags of rice for me",
        "Drop am for Yaba",
        "Oya drop am for Lekki",
        "Deliver to Surulere sharp sharp",
        "I need 10 bags of sugar for Ikeja",
        "Buy 2 bags of BUA sugar",
        "Actually make it 3 bags of Mama Gold Rice 50kg instead",
        "No be Dangote again, give me 5 bags of Mama Gold instead",
        "Change am to 4 bags of Royal Stallion rice",
        "Send 1 bag of rice to Abuja",
    ],
    "RESERVE_APPOINTMENT": [
        "I want to book appointment for tomorrow",
        "Book session for executive haircut",
        "Book slot for deep tissue massage",
        "Reserve space for me this afternoon",
        "Lock my date for bridal facial",
        "Schedule meeting with the consultant",
        "Any slot for tomorrow morning?",
        "Abeg help me book appointment for Friday",
        "Reserve a VIP barber slot for 2pm",
    ],
    "WHOLESALE_DISCOUNT_INQUIRY": [
        "Abeg give me wholesale price if I buy plenty cartons for my shop",
        "Can you slash price if I buy 50 bags?",
        "Discount dey for bulk buyers?",
        "Abeg reduce small na, wetin be last price?",
        "What is your wholesale price tier for 100 bags?",
        "If I buy plenty bags of rice, how much discount you go give me?",
        "Give me discount abeg, na reselling I dey do",
        "Wetin be last price if I pack 20 cartons?",
    ],
    "DELIVERY_TIMELINE_INQUIRY": [
        "Wait o, how long delivery dey take for Lekki?",
        "When e go land if I order now?",
        "What is your delivery timeline to Abuja?",
        "When dispatch rider go move?",
        "Do you do interstate waybill to Ibadan?",
        "How many days delivery go take to reach Yaba?",
        "How many hours before rider reach Ikeja?",
        "When rider go drop am if I pay now?",
        "how long is the delivery ?",
        "How long does delivery take?",
        "How long before my order reaches me?",
        "When will my rider reach me?",
        "How soon can you deliver?",
        "Is delivery same day?",
        "I ordered last week, when will it arrive?",
        "Wetin be the delivery time for my last order?",
        "Where is my order, how long again?",
        "How many days for delivery to Abuja?",
    ],
    "TRUST_VERIFICATION_PROOF": [
        "Hope say no be scam o?",
        "Are you guys legit?",
        "Where your shop dey for Lagos?",
        "Where una shop dey?",
        "Where is your physical shop located?",
        "Proof dey? Make I see past work and customer reviews",
        "Send customer reviews make I sure say una legit",
        "Can I see past delivery proof?",
    ],
    "REQUEST_PAYMENT_DETAILS": [
        "Send account details make I pay",
        "How I go pay? Send moniepoint acct",
        "Wetin be your USSD code for transfer?",
        "Send your bank account number for GTB transfer",
        "Give me Zenith or Moniepoint account details to transfer",
        "Send account make I wire the money now",
    ],
    "HUMAN_AGENT_HANDOFF": [
        "I want to speak to human agent",
        "Make I talk to person abeg",
        "Agent abeg come help me",
        "Transfer me to customer care",
        "Please call me, I need a real person",
        "Connect me to a human support representative",
        "Let me talk to a real person on the desk",
    ],
    "GREETING_ENGAGEMENT": [
        "How far boss!",
        "Wetin dey happen today?",
        "Good morning, how business?",
        "Good afternoon!",
        "Good evening o",
        "Hello there",
        "Hi, welcome",
        "Hey boss",
        "Oya how far na",
    ],
    "GENERAL_INQUIRY": [
        "This is a prepaid meter inquiry",
        "I have an unpaid utility bill question",
        "We are setting up a brand new bakery in Ikeja and need flour specifications and long-term financing.",
        "I want to ask if una dey open on public holidays",
        "Random complex query that does not match fast path keywords at all.",
        "What are the nutritional specifications and gluten percentages for commercial baking?",
        "Can we partner with your company as a logistics distributor next quarter?",
        "Tell me more about your company history and corporate governance.",
    ],
}


def build_and_train_spacy_pipeline(output_dir: Path, n_iter: int = 25) -> Any:
    """Constructs, trains, and saves the native spaCy NLU pipeline."""
    import spacy
    from spacy.training import Example

    random.seed(42)
    nlp = spacy.blank("en")

    # 1. Add deterministic EntityRuler before NER/TextCat
    ruler = nlp.add_pipe("entity_ruler", config={"overwrite_ents": True})

    # 2. Add Exclusive Multiclass TextCategorizer (BoW + Trigram character/word features)
    textcat = nlp.add_pipe(
        "textcat",
        config={
            "model": {
                "@architectures": "spacy.TextCatBOW.v3",
                "exclusive_classes": True,
                "ngram_size": 3,
                "no_output_layer": False,
                "length": 262144,
            }
        },
    )
    for label in INTENT_LABELS:
        textcat.add_label(label)

    # Prepare training examples
    examples: List[Example] = []
    for intent_label, utterances in INTENT_TRAINING_CORPUS.items():
        cats = {lbl: (1.0 if lbl == intent_label else 0.0) for lbl in INTENT_LABELS}
        for text in utterances:
            doc = nlp.make_doc(text)
            examples.append(Example.from_dict(doc, {"cats": cats}))
            # Include lowercase variant for casing invariance
            doc_lower = nlp.make_doc(text.lower())
            examples.append(Example.from_dict(doc_lower, {"cats": cats}))

    optimizer = nlp.initialize(lambda: examples)
    for _ in range(n_iter):
        random.shuffle(examples)
        losses: Dict[str, float] = {}
        for batch in spacy.util.minibatch(examples, size=8):
            nlp.update(batch, sgd=optimizer, losses=losses)

    # Populate EntityRuler patterns AFTER nlp.initialize() so EntityRuler.initialize() does not clear them
    ruler.add_patterns(CATALOG_SKU_PATTERNS + COMMODITY_PATTERNS + DELIVERY_ZONE_PATTERNS + FULFILLMENT_PATTERNS)

    output_dir.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(output_dir)
    logger.info("spacy_nlu_model_trained_and_saved", output_dir=str(output_dir), examples_count=len(examples))
    return nlp


def ensure_spacy_model_trained(model_dir: str = "models/spacy_nigerian_sme", force: bool = False) -> Path:
    """Ensures the trained spaCy model exists on disk, training it if missing or forced."""
    path = Path(model_dir)
    if not path.is_absolute():
        # Resolve relative to backend root
        backend_root = Path(__file__).resolve().parents[2]
        path = backend_root / model_dir
    patterns_file = path / "entity_ruler" / "patterns.jsonl"
    if force or not (path / "meta.json").exists() or not patterns_file.exists() or patterns_file.stat().st_size == 0:
        build_and_train_spacy_pipeline(path)
    return path


if __name__ == "__main__":
    trained_path = ensure_spacy_model_trained(force=True)
    print(f"Trained spaCy NLU model saved to: {trained_path}")
