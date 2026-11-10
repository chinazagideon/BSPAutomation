"""Structured JSON Application Logging with OpenTelemetry and ContextVars Binding."""

import sys
import logging
from typing import Optional, Any, Dict, Callable, List
import structlog

from app.core.config import settings
from app.core.telemetry import get_active_trace_id, get_active_span_id
from app.core.trace import get_context_merchant_id, get_trace_id


_TELEMETRY_SINKS: List[Callable[[Dict[str, Any]], None]] = []


def register_telemetry_sink(sink: Callable[[Dict[str, Any]], None]) -> None:
    """Registers a non-blocking callback to receive structured log event dictionaries."""
    if sink not in _TELEMETRY_SINKS:
        _TELEMETRY_SINKS.append(sink)


def unregister_telemetry_sink(sink: Callable[[Dict[str, Any]], None]) -> None:
    """Unregisters a previously registered telemetry sink."""
    if sink in _TELEMETRY_SINKS:
        _TELEMETRY_SINKS.remove(sink)


def telemetry_sink_processor(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Forwards a shallow clone of the enriched event dict to all registered telemetry sinks."""
    if _TELEMETRY_SINKS:
        # Clone snapshot so sinks cannot mutate the logged payload
        snapshot = dict(event_dict)
        for sink in list(_TELEMETRY_SINKS):
            try:
                sink(snapshot)
            except Exception:
                pass
    return event_dict


def otel_context_processor(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Injects distributed tracing metadata (trace_id, span_id) and multi-tenant
    context (merchant_id) into every log entry from active async context.
    """
    # 1. OpenTelemetry Trace ID or Fallback ContextVar Trace ID
    trace_id = get_active_trace_id() or get_trace_id()
    if trace_id and "trace_id" not in event_dict:
        event_dict["trace_id"] = trace_id

    # 2. OpenTelemetry Span ID
    span_id = get_active_span_id()
    if span_id and "span_id" not in event_dict:
        event_dict["span_id"] = span_id

    # 3. Tenant Merchant ID
    merchant_id = get_context_merchant_id()
    if merchant_id and "merchant_id" not in event_dict:
        event_dict["merchant_id"] = merchant_id

    return event_dict


def setup_logging() -> None:
    """Configures global structlog and standard library logging pipeline."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        otel_context_processor,
        telemetry_sink_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )


# Configure logging upon module import
setup_logging()


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Returns a structured logger instance bound to the specified component name."""
    logger = structlog.get_logger(name or "bsp")
    return logger
