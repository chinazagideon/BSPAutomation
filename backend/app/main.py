"""FastAPI Modular Monolith Application Entrypoint for Enterprise WhatsApp Platform."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from app.core.config import settings
from app.core.database import check_db_health

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
    print(f"[{settings.APP_NAME}] Starting up in {settings.ENVIRONMENT} mode...")
    print(f"[{settings.APP_NAME}] NLU State Controllers -> "
          f"FastPath={settings.USE_FAST_PATH} (Threshold={settings.FAST_PATH_CONFIDENCE_THRESHOLD}), "
          f"CustomModel={settings.USE_CUSTOM_MODEL} ({settings.CUSTOM_MODEL_TYPE}, Threshold={settings.CUSTOM_MODEL_CONFIDENCE_THRESHOLD}), "
          f"LLMEscalation={settings.USE_LLM_ESCALATION}")
    
    # DB Connectivity check
    is_db_healthy = await check_db_health()
    if is_db_healthy:
        print(f"[{settings.APP_NAME}] PostgreSQL Database connected successfully.")
    else:
        print(f"[{settings.APP_NAME}] PostgreSQL Database not reachable at {settings.DATABASE_URL}. (Using mock mode for tests/dev)")

    yield
    print(f"[{settings.APP_NAME}] Shutting down gracefully...")


# FastAPI Application Instance
app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise Conversational Workflow Platform for Nigerian SMEs",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Latency Header Middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response


# Mount Bounded Context Routers
app.include_router(core_router, prefix=settings.API_V1_PREFIX)
app.include_router(ingress_router, prefix=settings.API_V1_PREFIX)
app.include_router(ledger_router, prefix=settings.API_V1_PREFIX)
app.include_router(reservations_router, prefix=settings.API_V1_PREFIX)
app.include_router(desk_router, prefix=settings.API_V1_PREFIX)
app.include_router(compliance_router, prefix=settings.API_V1_PREFIX)


@app.get("/api/health", tags=["Health"])
async def health_check():
    """System health check endpoint providing service uptime and infrastructure status."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "nlu_pipeline": {
            "stage_1_fast_path": settings.USE_FAST_PATH,
            "stage_2_custom_model": settings.USE_CUSTOM_MODEL,
            "stage_3_llm_escalation": settings.USE_LLM_ESCALATION,
        },
        "adapters": {
            "payment": "MockMoniepoint" if settings.USE_MOCK_PAYMENT_GATEWAY else "MoniepointProduction",
            "whatsapp": "MockWhatsAppBSP" if settings.USE_MOCK_WHATSAPP_BSP else settings.WHATSAPP_BSP_PROVIDER,
        }
    }


@app.get("/", tags=["Health"])
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME} Backend API",
        "docs": "/docs",
        "health": "/api/health",
    }
