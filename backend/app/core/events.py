"""Typed Asynchronous Event Bus for Decoupled Cross-Context Communication."""

import asyncio
from typing import Callable, Dict, List, Any, Type, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid


from app.core.trace import get_trace_id
from app.core.telemetry import get_tracer, get_active_span_id
from app.core.logging import get_logger
from opentelemetry.trace import StatusCode

logger = get_logger("event_bus")


class DomainEvent(BaseModel):
    """Base domain event model for cross-context choreography with W3C TraceContext and lineage."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    merchant_id: str
    event_type: str
    trace_id: str = Field(default_factory=get_trace_id)
    span_id: str = Field(default_factory=get_active_span_id)
    causation_id: Optional[str] = None


class AgentHandoffRequestedEvent(DomainEvent):
    """Emitted by Ingress NLU when an inquiry requires human desk escalation."""
    event_type: str = "agent.handoff.requested"
    conversation_id: str
    customer_phone: str
    customer_name: Optional[str] = None
    summary_card_data: Dict[str, Any] = Field(default_factory=dict)
    detected_entities: Dict[str, Any] = Field(default_factory=dict)


class HubPowerOutageDetectedEvent(DomainEvent):
    """Emitted by Desk heartbeat monitor when all agents in a regional hub are OFFLINE_NEPA."""
    event_type: str = "hub.power_outage.detected"
    hub_id: Optional[str] = None
    hub_name: str
    open_ticket_count: int = 0
    is_reminder: bool = False
    reminder_count: int = 0
    outage_started_at: Optional[datetime] = None


class HubPowerRestoredEvent(DomainEvent):
    """Emitted when agents in a previously dark regional hub return online."""
    event_type: str = "hub.power_restored"
    hub_id: Optional[str] = None
    hub_name: str
    outage_duration_seconds: int = 0


class OutboundMessageRequestedEvent(DomainEvent):
    """Emitted to request dispatch of an audited outbound WhatsApp message."""
    event_type: str = "message.outbound.requested"
    conversation_id: str
    to_phone: str
    message_type: str = "text"  # text, template, media, interactive
    body_text: Optional[str] = None
    template_name: Optional[str] = None
    template_components: Optional[List[Dict[str, Any]]] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None  # document, image, audio
    caption: Optional[str] = None
    interactive_payload: Optional[Dict[str, Any]] = None


class FastPathDictionaryInvalidatedEvent(DomainEvent):
    """Emitted when merchant custom fast-path phrases are updated in PostgreSQL."""
    event_type: str = "fast_path.dictionary.invalidated"


class MerchantProviderContextUpdatedEvent(DomainEvent):
    """Emitted when active Meta WABA provider metadata (business hours, catalog ID) is updated."""
    event_type: str = "merchant.provider_context.updated"
    provider_context_data: Dict[str, Any] = Field(default_factory=dict)


class CatalogMissDetectedEvent(DomainEvent):
    """Emitted when a customer inquiry targets products missing from the merchant's catalog."""
    event_type: str = "catalog.miss.detected"
    customer_phone: str
    query_term: str
    raw_message: str
    detected_category: Optional[str] = None


class EventBus:
    """Asynchronous In-Process and Redis-backed Event Bus with OpenTelemetry Tracing."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable[[DomainEvent], Any]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], Any]) -> None:
        """Registers an asynchronous subscriber callback for a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Publishes a domain event to all registered listeners wrapped in an overarching publish span."""
        tracer = get_tracer("bsp-events")
        handlers = self._handlers.get(event.event_type, [])

        with tracer.start_as_current_span(f"event.publish:{event.event_type}") as pub_span:
            pub_span.set_attribute("bsp.event_id", event.event_id)
            pub_span.set_attribute("bsp.merchant_id", event.merchant_id)
            pub_span.set_attribute("bsp.event_type", event.event_type)
            if event.causation_id:
                pub_span.set_attribute("bsp.causation_id", event.causation_id)
            pub_span.set_attribute("bsp.subscribers_count", len(handlers))

            logger.info("event_published", event_type=event.event_type, event_id=event.event_id, merchant_id=event.merchant_id)

            if handlers:
                # Execute handlers concurrently in the current event loop with child spans
                tasks = [asyncio.create_task(self._safe_execute(handler, event)) for handler in handlers]
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_execute(self, handler: Callable[[DomainEvent], Any], event: DomainEvent) -> None:
        tracer = get_tracer("bsp-events")
        handler_name = getattr(handler, "__name__", str(handler))

        with tracer.start_as_current_span(f"event.handle:{event.event_type}:{handler_name}") as sub_span:
            sub_span.set_attribute("bsp.event_id", event.event_id)
            sub_span.set_attribute("bsp.merchant_id", event.merchant_id)
            sub_span.set_attribute("bsp.event_type", event.event_type)
            sub_span.set_attribute("bsp.handler", handler_name)

            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as err:
                sub_span.record_exception(err)
                sub_span.set_status(StatusCode.ERROR, str(err))
                logger.error(
                    "event_subscriber_failed",
                    event_type=event.event_type,
                    event_id=event.event_id,
                    handler=handler_name,
                    error=str(err),
                )
                print(f"[EventBus] Error executing subscriber for {event.event_type}: {err}")


# Global Event Bus Instance
event_bus = EventBus()
