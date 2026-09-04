"""FastAPI Modular Monolith Application Entrypoint for Enterprise WhatsApp Platform."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import check_db_health
from app.core.trace import get_trace_id
from app.core.response import ApiResponse, ApiErrorResponse
from app.core.middleware import (
    TraceContextMiddleware,
    ProcessTimeMiddleware,
    GlobalExceptionMiddleware,
    RateLimitMiddleware,
)

# Bounded Context Routers
from app.contexts.core.router import router as core_router
from app.contexts.ingress.router import router as ingress_router
from app.contexts.ledger.router import router as ledger_router
from app.contexts.reservations.router import router as reservations_router
from app.contexts.desk.router import router as desk_router
from app.contexts.compliance.router import router as compliance_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan lifecycle events."""
    from app.core.egress import create_pooled_http_client, AuditedHttpClient, set_default_audited_client
    from app.core.telemetry import init_telemetry, shutdown_telemetry
    from app.core.logging import get_logger

    # 0. Initialize OpenTelemetry & Structured Logging
    if settings.OTEL_ENABLED:
        init_telemetry(settings.OTEL_SERVICE_NAME)

    logger = get_logger("app.main")
    logger.info("app_starting", app_name=settings.APP_NAME, environment=settings.ENVIRONMENT)
    print(f"[{settings.APP_NAME}] NLU State Controllers -> "
          f"FastPath={settings.USE_FAST_PATH} (Threshold={settings.FAST_PATH_CONFIDENCE_THRESHOLD}), "
          f"CustomModel={settings.USE_CUSTOM_MODEL} ({settings.CUSTOM_MODEL_TYPE}, Threshold={settings.CUSTOM_MODEL_CONFIDENCE_THRESHOLD}), "
          f"LLMEscalation={settings.USE_LLM_ESCALATION}")

    # 1. Initialize Managed Egress Connection Pool
    pooled_httpx = create_pooled_http_client()
    audited_client = AuditedHttpClient(client=pooled_httpx)
    app.state.pooled_httpx = pooled_httpx
    app.state.audited_http_client = audited_client
    set_default_audited_client(audited_client)

    # 2. DB Connectivity check
    is_db_healthy = await check_db_health()
    if is_db_healthy:
        print(f"[{settings.APP_NAME}] PostgreSQL Database connected successfully.")
    else:
        print(f"[{settings.APP_NAME}] PostgreSQL Database not reachable at {settings.DATABASE_URL}. (Using mock mode for tests/dev)")

    yield

    print(f"[{settings.APP_NAME}] Shutting down gracefully...")
    # Teardown Managed Connection Pool
    if hasattr(app.state, "pooled_httpx"):
        await app.state.pooled_httpx.aclose()
        print(f"[{settings.APP_NAME}] Egress HTTP connection pool closed successfully.")

    # Teardown OpenTelemetry TracerProvider & Flush Spans
    if settings.OTEL_ENABLED:
        await shutdown_telemetry()


# FastAPI Application Instance
app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise Conversational Workflow Platform for Nigerian SMEs",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

if settings.OTEL_ENABLED:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception as err:
        print(f"[Telemetry] FastAPI instrumentation skipped: {err}")

# -----------------------------------------------------------------------------
# RFC 7807 HYBRID EXCEPTION HANDLERS (ADR-0028, ADR-0033)
# -----------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    trace_id = get_trace_id()
    err_resp = ApiErrorResponse.create(
        type_=f"urn:bsp:error:http_{exc.status_code}",
        title=exc.detail if isinstance(exc.detail, str) else "HTTP Exception",
        status_code=exc.status_code,
        detail=str(exc.detail),
        instance=str(request.url.path),
        trace_id=trace_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=err_resp.model_dump(mode="json", by_alias=True),
        headers={"X-Trace-ID": trace_id, **(getattr(exc, "headers", None) or {})},
    )


@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
    trace_id = get_trace_id()
    invalid_params = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    err_resp = ApiErrorResponse.create(
        type_="urn:bsp:error:validation_error",
        title="Unprocessable Entity",
        status_code=422,
        detail=str(exc.errors()),
        instance=str(request.url.path),
        invalid_params=invalid_params,
        trace_id=trace_id,
    )
    return JSONResponse(
        status_code=422,
        content=err_resp.model_dump(mode="json", by_alias=True),
        headers={"X-Trace-ID": trace_id},
    )


# -----------------------------------------------------------------------------
# GLOBAL MIDDLEWARE STACK (ADR-0028, ADR-0030)
# (Added in reverse order so TraceContext is the outermost layer)
# -----------------------------------------------------------------------------
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GlobalExceptionMiddleware)
app.add_middleware(ProcessTimeMiddleware)
app.add_middleware(TraceContextMiddleware)


# Mount Bounded Context Routers
app.include_router(core_router, prefix=settings.API_V1_PREFIX)
app.include_router(ingress_router, prefix=settings.API_V1_PREFIX)
app.include_router(ledger_router, prefix=settings.API_V1_PREFIX)
app.include_router(reservations_router, prefix=settings.API_V1_PREFIX)
app.include_router(desk_router, prefix=settings.API_V1_PREFIX)
app.include_router(compliance_router, prefix=settings.API_V1_PREFIX)


@app.get("/api/health", tags=["Health"], response_model=ApiResponse[dict])
async def health_check():
    """System health check endpoint providing service uptime and infrastructure status."""
    data = {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "nluPipeline": {
            "stage1FastPath": settings.USE_FAST_PATH,
            "stage2CustomModel": settings.USE_CUSTOM_MODEL,
            "stage3LlmEscalation": settings.USE_LLM_ESCALATION,
        },
        "adapters": {
            "payment": "MockMoniepoint" if settings.USE_MOCK_PAYMENT_GATEWAY else "MoniepointProduction",
            "whatsapp": "MockWhatsAppBSP" if settings.USE_MOCK_WHATSAPP_BSP else settings.WHATSAPP_BSP_PROVIDER,
        }
    }
    return ApiResponse.create(data=data)


@app.get("/", tags=["Health"], response_model=ApiResponse[dict])
async def root():
    data = {
        "message": f"Welcome to {settings.APP_NAME} Backend API",
        "docs": "/docs",
        "health": "/api/health",
    }
    return ApiResponse.create(data=data)


# -----------------------------------------------------------------------------
# Dependency Providers for Lifespan-Managed Egress
# -----------------------------------------------------------------------------

def get_audited_http_client(request: Request):
    """FastAPI dependency resolving the lifespan-managed AuditedHttpClient."""
    from app.core.egress import get_default_audited_client
    if hasattr(request.app.state, "audited_http_client"):
        return request.app.state.audited_http_client
    return get_default_audited_client()


def get_whatsapp_adapter(request: Request):
    """FastAPI dependency resolving WhatsAppBSPPort with lifespan-managed connection pool."""
    from app.adapters.whatsapp import get_whatsapp_bsp_adapter
    client = get_audited_http_client(request)
    return get_whatsapp_bsp_adapter(http_client=client)

