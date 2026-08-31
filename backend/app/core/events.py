"""Typed Asynchronous Event Bus for Decoupled Cross-Context Communication."""

import asyncio
from typing import Callable, Dict, List, Any, Type, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid


class DomainEvent(BaseModel):
    """Base domain event model for cross-context choreography."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    merchant_id: str
    event_type: str


class EventBus:
    """Asynchronous In-Process and Redis-backed Event Bus."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable[[DomainEvent], Any]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], Any]) -> None:
        """Registers an asynchronous subscriber callback for a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Publishes a domain event to all registered local and remote background listeners."""
        handlers = self._handlers.get(event.event_type, [])
        if handlers:
            # Execute handlers concurrently in the current event loop without blocking
            tasks = [asyncio.create_task(self._safe_execute(handler, event)) for handler in handlers]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_execute(self, handler: Callable[[DomainEvent], Any], event: DomainEvent) -> None:
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as err:
            print(f"[EventBus] Error executing subscriber for {event.event_type}: {err}")


# Global Event Bus Instance
event_bus = EventBus()
