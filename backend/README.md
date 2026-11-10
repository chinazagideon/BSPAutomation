# BSPAutomation — Backend Server

A multi-tenant Python **FastAPI & AsyncIO** backend for a Conversational Workflow Platform.

---

## 1. System Architecture

The backend is architected as a **Context-First Modular Monolith (Domain-Driven Design / Hexagonal)** strictly partitioning the 5 enterprise bounded contexts defined in `CONTEXT-MAP.md`:

## 2. 3-Stage Cascading Hybrid NLU Pipeline

Inbound customer messages pass through a 3-tier sequential cascading pipeline with dual confidence escalation gates and environment-driven state controllers:

```
[Inbound WhatsApp Message]
       │
       ▼
[Compliance PII Sanitizer]
       │
       ▼
[Stage 1: Fast-Path Router (pg_trgm & regex)] ──(Confidence >= 0.90)──► [Instant Response: 0 tokens, ~2ms]
       │ (Confidence < 0.90)
       ▼
[Stage 2: Custom Local Model (HuggingFace/ONNX)] ──(Confidence >= 0.75)──► [Template Response: 0 tokens, ~20ms]
       │ (Confidence < 0.75)
       ▼
[Stage 3: Gemini 3.7 Flash Escalation] ──(AI Wallet Debit)──► [LLM Synthesis: 400 tokens, ~380ms]
       │ (If LLM Disabled / Offline)
       ▼
[Graceful Fallback: Human Agent Desk Handoff]
```

### Environment State Controllers
Configure pipeline execution in `.env`:
```bash
# Stage 1: Deterministic Trigram Fast-Path
USE_FAST_PATH=true
FAST_PATH_CONFIDENCE_THRESHOLD=0.90

# Stage 2: Custom Local Classifier (HuggingFace / ONNX)
USE_CUSTOM_MODEL=true
CUSTOM_MODEL_TYPE=mock                 # mock | onnx | transformers
CUSTOM_MODEL_PATH=models/nigerian_pidgin_intent
CUSTOM_MODEL_CONFIDENCE_THRESHOLD=0.75

# Stage 3: LLM Escalation (Google Gemini 3.7 Flash)
USE_LLM_ESCALATION=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.7-flash
```

---

## 3. Quickstart with Docker Compose

Run the complete multi-container stack with a single command:

```bash
docker compose up --build
```

This launches:
1. `bsp_postgres`: PostgreSQL 16 Alpine with `001_enterprise_schema.sql` automatically provisioned on port `5432`.
2. `bsp_redis`: Redis 7 Alpine for ARQ job queue on port `6379`.
3. `bsp_api`: FastAPI application with hot-reloading on `http://localhost:8000`.
4. `bsp_worker`: ARQ background worker for asynchronous webhook scoring and hold expiration crons.

---

## 4. Local Development Setup (Without Docker)

```bash
# 1. Navigate to backend directory
cd backend

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env

# 5. Start FastAPI application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Start ARQ Background Worker (in separate terminal)
arq app.core.worker.WorkerSettings
```

---

## 5. Running the Test Suite

```bash
cd backend
pytest -v
```

---

## 6. API Documentation & Interactive Explorer

- Interactive Swagger UI: `http://localhost:8000/docs`
- ReDoc Explorer: `http://localhost:8000/redoc`
- System Health Check: `http://localhost:8000/api/health`
