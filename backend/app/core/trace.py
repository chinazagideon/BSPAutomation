"""Distributed Trace Context Propagation using Python ContextVars."""

import uuid
from contextvars import ContextVar
from typing import Optional

_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")
_merchant_id_ctx: ContextVar[str] = ContextVar("merchant_id", default="")


def get_trace_id() -> str:
    """Retrieves the current async context trace_id or generates a new one."""
    val = _trace_id_ctx.get()
    if not val:
        val = str(uuid.uuid4())
        _trace_id_ctx.set(val)
    return val


def set_trace_id(trace_id: str) -> None:
    """Sets the active trace_id in the current asynchronous context."""
    _trace_id_ctx.set(trace_id)


def get_context_merchant_id() -> Optional[str]:
    """Retrieves the active merchant_id in the current context."""
    return _merchant_id_ctx.get() or None


def set_context_merchant_id(merchant_id: str) -> None:
    """Sets the active merchant_id in the current context."""
    _merchant_id_ctx.set(merchant_id)
