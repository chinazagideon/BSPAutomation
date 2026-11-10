"""Centralized OpenTelemetry Tracing Engine, W3C TraceContext Propagation, and Sampling Lifecycle."""

import logging
from typing import Optional, Dict, Any
from opentelemetry import trace
from opentelemetry.trace import Tracer, Span, StatusCode, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased, ALWAYS_ON
from opentelemetry.sdk.resources import Resource

from app.core.config import settings

logger = logging.getLogger(__name__)

_TRACER_PROVIDER: Optional[TracerProvider] = None
_PROPAGATOR = TraceContextTextMapPropagator()


def get_tracer(name: str = "bsp-whatsapp") -> Tracer:
    """Returns an OpenTelemetry Tracer instance from the global provider."""
    return trace.get_tracer(name)


def get_active_trace_id() -> str:
    """Returns the current active span trace_id formatted as a 32-character hex string."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return ""


def get_active_span_id() -> str:
    """Returns the current active span_id formatted as a 16-character hex string."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return format(ctx.span_id, "016x")
    return ""


def inject_trace_context(carrier: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Injects the active OpenTelemetry context into a carrier dictionary
    following the W3C TraceContext standard (e.g. 'traceparent': '00-...').
    """
    if carrier is None:
        carrier = {}
    _PROPAGATOR.inject(carrier)
    return carrier


def extract_trace_context(carrier: Dict[str, str]):
    """
    Extracts an OpenTelemetry Context from a carrier dictionary containing
    W3C 'traceparent' / 'tracestate' headers or job metadata.
    """
    return _PROPAGATOR.extract(carrier)


def init_telemetry(service_name: Optional[str] = None) -> TracerProvider:
    """
    Initializes the OpenTelemetry TracerProvider with environment-appropriate
    samplers, resources, and exporters.
    """
    global _TRACER_PROVIDER
    if _TRACER_PROVIDER is not None:
        return _TRACER_PROVIDER

    svc_name = service_name or settings.OTEL_SERVICE_NAME
    resource = Resource.create({
        "service.name": svc_name,
        "deployment.environment": settings.ENVIRONMENT,
        "service.version": "1.0.0",
    })

    # Sampling Strategy:
    # Development/Test: 100% AlwaysOn
    # Staging/Production: ParentBased with configurable TraceIdRatioBased
    if settings.ENVIRONMENT in ["development", "test"]:
        sampler = ALWAYS_ON
    else:
        ratio = max(0.01, min(1.0, settings.OTEL_SAMPLING_RATIO))
        sampler = ParentBased(root=TraceIdRatioBased(ratio))

    provider = TracerProvider(resource=resource, sampler=sampler)

    # Exporter Setup:
    if settings.ENVIRONMENT == "test":
        # Silent during test runs
        pass
    else:
        # Development / Staging / Production: Export to OTLP collector if configured
        if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                otlp_exporter = OTLPSpanExporter(
                    endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
                    insecure=True,
                )
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"[Telemetry] Initialized OTLP gRPC exporter -> {settings.OTEL_EXPORTER_OTLP_ENDPOINT}")
            except Exception as err:
                logger.warning(f"[Telemetry] Could not initialize OTLP exporter: {err}")

    trace.set_tracer_provider(provider)
    _TRACER_PROVIDER = provider
    return provider


async def shutdown_telemetry() -> None:
    """Flushes in-flight spans and shuts down the global TracerProvider."""
    global _TRACER_PROVIDER
    if _TRACER_PROVIDER is not None:
        try:
            _TRACER_PROVIDER.shutdown()
        except Exception as err:
            logger.error(f"[Telemetry] Error shutting down TracerProvider: {err}")
        finally:
            _TRACER_PROVIDER = None
