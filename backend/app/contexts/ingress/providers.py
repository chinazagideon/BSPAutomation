"""Ingress Customer History Context Provider (ADR-0041)."""

import re
from typing import Dict, Any, Optional, Sequence, Union
from uuid import UUID

from app.contexts.ingress.schemas import DialogueTurn
from app.core.generation.context import ContextProvider, ContextSlice

_DIVIDER_RE = re.compile(r"[━─]{3,}")


def format_dialogue_turn(turn: Union[DialogueTurn, str]) -> str:
    """Formats a DialogueTurn or legacy raw string into a role-attributed history line."""
    if isinstance(turn, DialogueTurn):
        label = "Customer" if turn.role == "customer" else "Assistant"
        return f"[{label}]: {turn.text}"
    cleaned = _DIVIDER_RE.sub("", str(turn or ""))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return f"- {cleaned}"


class CustomerHistorySliceProvider(ContextProvider):
    """Provides recent customer conversational history for generation context."""

    @property
    def slice_name(self) -> str:
        return "customer_history"

    async def resolve(
        self,
        merchant_id: Optional[UUID],
        customer_phone: Optional[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> ContextSlice:
        opts = options or {}
        recent_messages: Sequence[Union[DialogueTurn, str]] = opts.get("previous_context") or []
        customer_name = opts.get("customer_name", "Valued Customer")

        if not recent_messages:
            content = f"Customer Name: {customer_name}\nCustomer Phone: {customer_phone or 'N/A'}\nNo previous chat history."
        else:
            turns = "\n".join(format_dialogue_turn(m) for m in recent_messages[-5:])
            content = f"Customer Name: {customer_name}\nCustomer Phone: {customer_phone or 'N/A'}\nRecent Turns:\n{turns}"

        token_est = max(10, len(content.split()) * 2)
        return ContextSlice(
            slice_name=self.slice_name,
            content=content,
            structured_data={"recent_turns_count": len(recent_messages)},
            token_estimate=token_est,
        )
