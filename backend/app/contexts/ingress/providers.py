"""Ingress Customer History Context Provider (ADR-0041)."""

from typing import Dict, Any, Optional
from uuid import UUID

from app.core.generation.context import ContextProvider, ContextSlice


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
        recent_messages = opts.get("previous_context", [])
        customer_name = opts.get("customer_name", "Valued Customer")

        if not recent_messages:
            content = f"Customer Name: {customer_name}\nCustomer Phone: {customer_phone or 'N/A'}\nNo previous chat history."
        else:
            turns = "\n".join(f"- {m}" for m in recent_messages[-5:])
            content = f"Customer Name: {customer_name}\nCustomer Phone: {customer_phone or 'N/A'}\nRecent Turns:\n{turns}"

        token_est = max(10, len(content.split()) * 2)
        return ContextSlice(
            slice_name=self.slice_name,
            content=content,
            structured_data={"recent_turns_count": len(recent_messages)},
            token_estimate=token_est,
        )
