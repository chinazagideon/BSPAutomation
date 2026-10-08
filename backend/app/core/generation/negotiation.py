"""Ephemeral Redis Negotiation Frame Manager (ADR-0043).

Enforces NDPA 2023 PII protection:
- Phone numbers are cryptographically hashed in Redis keys and stored frames.
- All stored slot values are scrubbed with sanitize_nigerian_pii_detailed.
- Manages 15-minute sliding TTL, Direct Button ID Slot Binding, and Frame Preservation.
"""

import time
import json
import re
from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel, Field
import structlog

from app.core.security import compute_sha256_hash
from app.contexts.compliance.services import sanitize_nigerian_pii_detailed
from app.core.redis import get_redis_client

logger = structlog.get_logger(__name__)

FRAME_TTL_SECONDS = 900  # 15 minutes per ADR-0043

CANCELLATION_REGEX = re.compile(
    r"\b(cancel(?:\s+am|\s+order|\s+it)?|never\s*mind|no\s*buy\s*again|i\s*no\s*(?:wan|dey)\s*buy|forget\s*(?:am|it)|abort|drop\s*am)\b",
    re.IGNORECASE
)


class NegotiationFrame(BaseModel):
    """Ephemeral session state machine tracking slot parameter accumulation and pending offers."""
    merchant_id: str
    phone_hash: str
    active_tool: str
    intent: str
    bound_slots: Dict[str, Any] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    pending_offer: Optional[Dict[str, Any]] = None
    created_at: float = Field(default_factory=time.time)
    last_updated: float = Field(default_factory=time.time)
    revision: int = 1


AFFIRMATION_REGEX = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|k|oya|sure|sharp|send\s*am|pls\s*do|please\s*do|correct|proceed|confirm|carry\s*go|abeg\s*send)\b",
    re.IGNORECASE
)

NEGATION_REGEX = re.compile(
    r"^(?:no|nah|nope|leave\s*am|never\s*mind|i\s*no\s*(?:wan|dey)\s*buy|i\s*no\s*want|forget\s*(?:am|it)|abort|cancel)\b",
    re.IGNORECASE
)


def compute_phone_hash(merchant_id: str, phone: str) -> str:
    """Computes a salted deterministic hash of the customer phone number for Redis keys."""
    raw = f"{merchant_id}:{phone.strip()}"
    return compute_sha256_hash(raw)[:16]


# In-memory fallback dictionary for testing or when Redis is offline
_IN_MEMORY_FRAME_CACHE: Dict[str, Tuple[NegotiationFrame, float]] = {}


class NegotiationFrameManager:
    """Manages ephemeral multi-turn negotiation frames in Redis."""

    @staticmethod
    def _build_redis_key(merchant_id: str, phone_hash: str) -> str:
        return f"merchant:{merchant_id}:negotiation:{phone_hash}"

    @classmethod
    async def get_frame(cls, merchant_id: str, customer_phone: str) -> Optional[NegotiationFrame]:
        """Retrieves active negotiation frame if still within the 15-minute TTL window."""
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        key = cls._build_redis_key(merchant_id, phone_hash)

        try:
            redis = await get_redis_client()
            raw_data = await redis.get(key)
            if raw_data:
                parsed = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                return NegotiationFrame(**parsed)
        except Exception as err:
            logger.warning("redis_frame_get_fallback", error=str(err))

        # Check in-memory fallback
        if key in _IN_MEMORY_FRAME_CACHE:
            frame, expiry = _IN_MEMORY_FRAME_CACHE[key]
            if time.time() <= expiry:
                return frame
            _IN_MEMORY_FRAME_CACHE.pop(key, None)

        return None

    @classmethod
    async def save_frame(
        cls,
        merchant_id: str,
        customer_phone: str,
        frame: NegotiationFrame,
        ttl: int = FRAME_TTL_SECONDS,
    ) -> None:
        """Saves or updates negotiation frame, scrubbing all slots for PII."""
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        key = cls._build_redis_key(merchant_id, phone_hash)

        # Scrub all string slots for PII
        sanitized_bound: Dict[str, Any] = {}
        for k, v in frame.bound_slots.items():
            if isinstance(v, str):
                cleaned, _ = sanitize_nigerian_pii_detailed(v)
                sanitized_bound[k] = cleaned
            else:
                sanitized_bound[k] = v

        frame.bound_slots = sanitized_bound
        frame.phone_hash = phone_hash
        frame.last_updated = time.time()
        frame.revision += 1

        payload_str = frame.model_dump_json()

        try:
            redis = await get_redis_client()
            await redis.set(key, payload_str, ex=ttl)
        except Exception as err:
            logger.warning("redis_frame_save_fallback", error=str(err))

        _IN_MEMORY_FRAME_CACHE[key] = (frame, time.time() + ttl)

    @classmethod
    async def evict_frame(cls, merchant_id: str, customer_phone: str) -> bool:
        """Explicitly deletes the negotiation frame on cancellation or completion."""
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        key = cls._build_redis_key(merchant_id, phone_hash)
        evicted = False

        try:
            redis = await get_redis_client()
            res = await redis.delete(key)
            evicted = (res > 0)
        except Exception as err:
            logger.warning("redis_frame_evict_fallback", error=str(err))

        if key in _IN_MEMORY_FRAME_CACHE:
            _IN_MEMORY_FRAME_CACHE.pop(key, None)
            evicted = True

        return evicted

    @classmethod
    async def touch_frame(cls, merchant_id: str, customer_phone: str, ttl: int = FRAME_TTL_SECONDS) -> None:
        """Extends TTL of an active frame (Frame Preservation on topic shifts)."""
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        key = cls._build_redis_key(merchant_id, phone_hash)

        try:
            redis = await get_redis_client()
            await redis.expire(key, ttl)
        except Exception:
            pass

        if key in _IN_MEMORY_FRAME_CACHE:
            frame, _ = _IN_MEMORY_FRAME_CACHE[key]
            _IN_MEMORY_FRAME_CACHE[key] = (frame, time.time() + ttl)

    @staticmethod
    def parse_interactive_id(interactive_id: Optional[str]) -> Optional[Tuple[str, Any]]:
        """
        Parses direct slot binding from WhatsApp interactive button/list IDs.
        Format: SET_SLOT:{slot_name}:{slot_value}
        Example: SET_SLOT:sku:SUGAR_DANGOTE_50KG -> ("sku", "SUGAR_DANGOTE_50KG")
        """
        if not interactive_id or not interactive_id.startswith("SET_SLOT:"):
            return None
        parts = interactive_id.split(":", 2)
        if len(parts) == 3:
            slot_name = parts[1].strip()
            slot_val = parts[2].strip()
            return slot_name, slot_val
        return None

    @staticmethod
    def is_cancellation_intent(text: str) -> bool:
        """Determines if the inbound message contains an explicit cancellation command."""
        return bool(CANCELLATION_REGEX.search(text.strip()))

    @staticmethod
    def is_affirmation_intent(text: str) -> bool:
        """Determines if the inbound message contains an explicit affirmation (yes, ok, oya, sure, etc.)."""
        return bool(AFFIRMATION_REGEX.search(text.strip()))

    @staticmethod
    def is_negation_intent(text: str) -> bool:
        """Determines if the inbound message contains an explicit negation (no, never mind, leave am, etc.)."""
        return bool(NEGATION_REGEX.search(text.strip()))

    @classmethod
    async def debounce_incoming_message(
        cls,
        merchant_id: str,
        customer_phone: str,
        raw_text: str,
        debounce_window_seconds: float = 1.2,
    ) -> str:
        """
        Concatenates rapid bursts within 1.2s debounce window per ADR-0043.
        Returns concatenated text if multiple messages arrived, or the original text.
        """
        import asyncio
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        buffer_key = f"merchant:{merchant_id}:debounce:{phone_hash}"
        lock_key = f"merchant:{merchant_id}:debounce_lock:{phone_hash}"

        try:
            redis = await get_redis_client()
            await redis.rpush(buffer_key, raw_text)
            await redis.expire(buffer_key, 10)
            acquired = await redis.set(lock_key, "1", nx=True, px=int(debounce_window_seconds * 1000) + 500)
            if acquired:
                await asyncio.sleep(debounce_window_seconds)
                items = await redis.lrange(buffer_key, 0, -1)
                await redis.delete(buffer_key)
                await redis.delete(lock_key)
                if items:
                    return "\n".join(items)
            else:
                # Another job is holding the debounce lock and will process our pushed text
                return ""
        except Exception as err:
            logger.warning("debounce_buffer_fallback", error=str(err))

        return raw_text

