"""Ephemeral Redis LIFO Context Stack & Negotiation Frame Repository (ADR-0043).

Enforces NDPA 2023 PII protection & Pydantic v2 Rich Domain Model Invariants:
- Phone numbers are cryptographically hashed in Redis keys and stored frames.
- All stored slot values are declaratively scrubbed via PiiSanitizedSlotMap.
- ContextStack encapsulates LIFO push/pop/peek, lazy per-node TTL pruning, intent deduplication,
  and MAX_STACK_DEPTH capping.
- NegotiationFrameManager is a thin Redis persistence repository.
"""

import asyncio
import re
import time
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, computed_field, field_validator
import structlog

from app.adapters.base import (
    InteractiveProtocolEnvelope,
    PiiSanitizedSlotMap,
    SlotBindAction,
)
from app.core.config import settings
from app.core.redis import get_redis_client
from app.core.security import compute_sha256_hash

logger = structlog.get_logger(__name__)

FRAME_TTL_SECONDS = settings.FSM_NODE_TTL_SECONDS

CANCELLATION_REGEX = re.compile(
    r"\b(cancel(?:\s+am|\s+order|\s+it)?|never\s*mind|no\s*buy\s*again|i\s*no\s*(?:wan|dey)\s*buy|forget\s*(?:am|it)|abort)\b",
    re.IGNORECASE,
)

AFFIRMATION_REGEX = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|k|oya|sure|sharp|send\s*am|pls\s*do|please\s*do|correct|proceed|confirm|carry\s*go|abeg\s*send)\b",
    re.IGNORECASE,
)

NEGATION_REGEX = re.compile(
    r"^(?:no|nah|nope|leave\s*am|never\s*mind|i\s*no\s*(?:wan|dey)\s*buy|i\s*no\s*want|forget\s*(?:am|it)|abort|cancel)\b",
    re.IGNORECASE,
)


def compute_phone_hash(merchant_id: str, phone: str) -> str:
    """Computes a salted deterministic hash of the customer phone number for Redis keys."""
    raw = f"{merchant_id}:{phone.strip()}"
    return compute_sha256_hash(raw)[:16]


class NegotiationFrame(BaseModel):
    """Ephemeral session state node tracking slot parameter accumulation and pending offers."""
    merchant_id: str
    phone_hash: str = ""
    active_tool: str = "CheckoutOrderTool"
    intent: str = "INSTANT_CHECKOUT_ORDER"
    node_type: Literal["TRANSACTIONAL", "ATOMIC_QUERY", "HANDOFF"] = "TRANSACTIONAL"
    bound_slots: PiiSanitizedSlotMap = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    pending_offer: Optional[Dict[str, Any]] = None
    created_at: float = Field(default_factory=time.time)
    last_updated: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + FRAME_TTL_SECONDS)
    revision: int = 1

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) > self.expires_at

    def refresh_ttl(self, ttl: int = FRAME_TTL_SECONDS) -> None:
        now = time.time()
        self.last_updated = now
        self.expires_at = now + ttl
        self.revision += 1


class ContextStack(BaseModel):
    """Rich Pydantic v2 LIFO Context Stack domain model (bottom -> top)."""
    merchant_id: str
    phone_hash: str
    max_depth: int = Field(default_factory=lambda: settings.FSM_STACK_MAX_DEPTH)
    frames: List[NegotiationFrame] = Field(default_factory=list)

    @field_validator("frames", mode="after")
    @classmethod
    def _prune_expired_and_cap_depth(cls, frames: List[NegotiationFrame]) -> List[NegotiationFrame]:
        now = time.time()
        live = [f for f in frames if not f.is_expired(now)]
        max_d = settings.FSM_STACK_MAX_DEPTH
        return live[-max_d:] if len(live) > max_d else live

    @computed_field
    @property
    def active_frame(self) -> Optional[NegotiationFrame]:
        return self.frames[-1] if self.frames else None

    def peek(self) -> Optional[NegotiationFrame]:
        self.frames = self._prune_expired_and_cap_depth(self.frames)
        return self.active_frame

    def push(self, frame: NegotiationFrame, ttl: int = FRAME_TTL_SECONDS) -> NegotiationFrame:
        # Validate bound_slots through NegotiationFrame model validation to ensure PII scrubbing
        validated_frame = NegotiationFrame.model_validate(frame.model_dump())
        validated_frame.phone_hash = self.phone_hash
        validated_frame.refresh_ttl(ttl)
        now = time.time()
        # Deduplicate existing frame with the same intent and prune expired nodes
        self.frames = [
            f for f in self.frames
            if not f.is_expired(now) and f.intent != validated_frame.intent
        ]
        self.frames.append(validated_frame)
        if len(self.frames) > self.max_depth:
            self.frames = self.frames[-self.max_depth:]
        return validated_frame

    def pop(self) -> Optional[NegotiationFrame]:
        self.frames = self._prune_expired_and_cap_depth(self.frames)
        return self.frames.pop() if self.frames else None


# In-memory fallback dictionary for testing or when Redis is offline
_IN_MEMORY_STACK_CACHE: Dict[str, Tuple[str, float]] = {}


class NegotiationFrameManager:
    """Thin Redis persistence repository for ContextStack."""

    @staticmethod
    def _build_redis_key(merchant_id: str, phone_hash: str) -> str:
        return f"merchant:{merchant_id}:negotiation:{phone_hash}"

    @classmethod
    async def load_stack(cls, merchant_id: str, customer_phone: str) -> ContextStack:
        """Loads and self-validates the LIFO ContextStack from Redis (lazily pruning expired frames)."""
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        key = cls._build_redis_key(merchant_id, phone_hash)

        raw_data: Optional[str] = None
        try:
            redis = await get_redis_client()
            val = await redis.get(key)
            if val:
                raw_data = val if isinstance(val, str) else val.decode("utf-8")
        except Exception as err:
            logger.warning("redis_stack_load_fallback", error=str(err))

        if not raw_data and key in _IN_MEMORY_STACK_CACHE:
            cached_json, expiry = _IN_MEMORY_STACK_CACHE[key]
            if time.time() <= expiry:
                raw_data = cached_json
            else:
                _IN_MEMORY_STACK_CACHE.pop(key, None)

        if raw_data:
            try:
                return ContextStack.model_validate_json(raw_data)
            except Exception:
                # Backwards compatibility if a single legacy NegotiationFrame was stored
                try:
                    single = NegotiationFrame.model_validate_json(raw_data)
                    return ContextStack(merchant_id=merchant_id, phone_hash=phone_hash, frames=[single])
                except Exception:
                    pass

        return ContextStack(merchant_id=merchant_id, phone_hash=phone_hash)

    @classmethod
    async def save_stack(
        cls,
        merchant_id: str,
        customer_phone: str,
        stack: ContextStack,
        ttl: int = FRAME_TTL_SECONDS,
    ) -> ContextStack:
        """Persists ContextStack to Redis or evicts the key if empty."""
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        key = cls._build_redis_key(merchant_id, phone_hash)
        stack.phone_hash = phone_hash
        stack.peek()

        if not stack.frames:
            await cls.evict_frame(merchant_id, customer_phone)
            return stack

        payload_str = stack.model_dump_json()
        max_expiry = max(int(f.expires_at - time.time()) for f in stack.frames)
        effective_ttl = max(1, max(ttl, max_expiry))

        try:
            redis = await get_redis_client()
            await redis.set(key, payload_str, ex=effective_ttl)
        except Exception as err:
            logger.warning("redis_stack_save_fallback", error=str(err))

        _IN_MEMORY_STACK_CACHE[key] = (payload_str, time.time() + effective_ttl)
        return stack

    @classmethod
    async def get_frame(cls, merchant_id: str, customer_phone: str) -> Optional[NegotiationFrame]:
        """Returns the active top-of-stack frame (peek)."""
        stack = await cls.load_stack(merchant_id, customer_phone)
        return stack.active_frame

    @classmethod
    async def get_stack_frames(cls, merchant_id: str, customer_phone: str) -> List[NegotiationFrame]:
        """Returns all non-expired frames in the LIFO ContextStack (bottom -> top)."""
        stack = await cls.load_stack(merchant_id, customer_phone)
        return list(stack.frames)

    @classmethod
    async def save_frame(
        cls,
        merchant_id: str,
        customer_phone: str,
        frame: NegotiationFrame,
        ttl: int = FRAME_TTL_SECONDS,
    ) -> None:
        """Pushes/updates the frame at the top of the LIFO ContextStack."""
        stack = await cls.load_stack(merchant_id, customer_phone)
        stack.push(frame, ttl=ttl)
        await cls.save_stack(merchant_id, customer_phone, stack, ttl=ttl)

    @classmethod
    async def push_frame(
        cls,
        merchant_id: str,
        customer_phone: str,
        frame: NegotiationFrame,
        ttl: int = FRAME_TTL_SECONDS,
    ) -> NegotiationFrame:
        """Explicit LIFO push operation."""
        stack = await cls.load_stack(merchant_id, customer_phone)
        pushed = stack.push(frame, ttl=ttl)
        await cls.save_stack(merchant_id, customer_phone, stack, ttl=ttl)
        return pushed

    @classmethod
    async def pop_frame(cls, merchant_id: str, customer_phone: str) -> Optional[NegotiationFrame]:
        """Explicit LIFO pop operation returning the popped frame and persisting remaining stack."""
        stack = await cls.load_stack(merchant_id, customer_phone)
        popped = stack.pop()
        await cls.save_stack(merchant_id, customer_phone, stack)
        return popped

    @classmethod
    async def evict_frame(cls, merchant_id: str, customer_phone: str) -> bool:
        """Deletes the entire session ContextStack on full completion or cancellation."""
        phone_hash = compute_phone_hash(merchant_id, customer_phone)
        key = cls._build_redis_key(merchant_id, phone_hash)
        evicted = False

        try:
            redis = await get_redis_client()
            res = await redis.delete(key)
            evicted = res > 0
        except Exception as err:
            logger.warning("redis_frame_evict_fallback", error=str(err))

        if key in _IN_MEMORY_STACK_CACHE:
            _IN_MEMORY_STACK_CACHE.pop(key, None)
            evicted = True

        return evicted

    @classmethod
    async def touch_frame(cls, merchant_id: str, customer_phone: str, ttl: int = FRAME_TTL_SECONDS) -> None:
        """Refreshes TTL on the active top-of-stack frame."""
        stack = await cls.load_stack(merchant_id, customer_phone)
        top = stack.peek()
        if top:
            top.refresh_ttl(ttl)
            await cls.save_stack(merchant_id, customer_phone, stack, ttl=ttl)

    @staticmethod
    def parse_interactive_id(interactive_id: Optional[str]) -> Optional[Tuple[str, Any]]:
        """Parses direct slot binding using InteractiveProtocolEnvelope Discriminated Union."""
        if not interactive_id:
            return None
        envelope = InteractiveProtocolEnvelope.model_validate(interactive_id)
        if isinstance(envelope.event, SlotBindAction):
            return envelope.event.slot_name, envelope.event.slot_value
        return None

    @staticmethod
    def is_cancellation_intent(text: str) -> bool:
        """Determines if the inbound message contains an explicit cancellation command (disambiguating 'drop am for [loc]')."""
        cleaned = (text or "").strip().lower()
        if CANCELLATION_REGEX.search(cleaned):
            return True
        if re.search(r"\bdrop\s*am\b", cleaned) and not re.search(r"\bdrop\s*am\s*(?:for|to|at|in)\b", cleaned):
            return True
        return False

    @staticmethod
    def is_affirmation_intent(text: str) -> bool:
        return bool(AFFIRMATION_REGEX.search((text or "").strip()))

    @staticmethod
    def is_negation_intent(text: str) -> bool:
        return bool(NEGATION_REGEX.search((text or "").strip()))

    @classmethod
    async def debounce_incoming_message(
        cls,
        merchant_id: str,
        customer_phone: str,
        raw_text: str,
        debounce_window_seconds: float = settings.DEBOUNCE_WINDOW_SECONDS,
    ) -> str:
        """Concatenates rapid bursts within debounce window."""
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
                    decoded = [m if isinstance(m, str) else m.decode("utf-8") for m in items]
                    deduped = [
                        m for idx, m in enumerate(decoded)
                        if idx == 0 or m.strip() != decoded[idx - 1].strip()
                    ]
                    return "\n".join(deduped)
            else:
                return ""
        except Exception as err:
            logger.warning("debounce_buffer_fallback", error=str(err))

        return raw_text
