# KudiFlow (BSPAutomation) — Full-Stack Conversational Workflow Platform & Sandbox

A multi-tenant **WhatsApp Conversational Workflow Platform** for Nigerian SMEs, pairing an interactive **React 19 + TypeScript + TanStack Query Sandbox Frontend** with a high-concurrency **Python FastAPI & AsyncIO Hexagonal Backend**.

---

## 1. Repository Architecture

The workspace combines a full-featured **Local BSP Sandbox & Observability Workbench (`src/` + `server.ts`)** with a **Context-First Modular Monolith Backend (`backend/`)** strictly partitioning the 5 enterprise bounded contexts defined in `CONTEXT-MAP.md`:

```text
BSP-WhatsApp/
├── src/                                  # React 19 + TypeScript Sandbox Frontend
│   ├── App.tsx                           # Multi-tab workbench container & state orchestration
│   ├── main.tsx                          # React 19 + TanStack QueryClientProvider entrypoint
│   ├── types.ts                          # Shared domain & sandbox TypeScript interfaces
│   ├── config/
│   │   └── env.ts                        # Environment-driven configuration (VITE_* variables)
│   ├── lib/
│   │   └── apiClient.ts                  # Typed HTTP client for /api/v1/sandbox/* & /api/*
│   ├── hooks/
│   │   ├── useSandboxApi.ts              # TanStack Query (useQuery / useMutation) hooks
│   │   └── useSandboxStream.ts           # Dedicated SSE (EventSource) real-time stream hook
│   └── components/
│       ├── Header.tsx                    # Top navigation bar & real-time telemetry counters
│       ├── WhatsAppPhoneSimulator.tsx    # Interactive WhatsApp phone shell & control workbench
│       ├── simulator/                    # Composable SRP simulator sub-components
│       │   ├── SimulatorControlBar.tsx   # Backend connection status, merchant & BSP selector
│       │   ├── ScenarioPresetsPanel.tsx  # 1-click Nigerian Pidgin & commercial test scenarios
│       │   ├── FaultInjectionPanel.tsx   # Chaos engineering (429/500, 24h window, burst, HMAC)
│       │   ├── NluFrameInspectorPanel.tsx# Live 3-stage NLU toggles & slot-filling frame viewer
│       │   ├── PhoneChatBubble.tsx       # WhatsApp message bubble, buttons, carousels & NUBAN cards
│       │   └── InteractiveListDrawer.tsx # Native WhatsApp bottom-sheet list drawer
│       ├── WebhookInspector.tsx          # Multi-provider webhook log stream & payload synthesizer
│       ├── NluIntentMatrix.tsx           # Live lead scoring, dialect detection & NLU playground
│       ├── AntiGhostingLedger.tsx        # Virtual NUBAN holds & 4-leg double-entry accounting
│       ├── AtomicReservationGrid.tsx     # GiST anti-double-booking calendar & 10-min hold timer
│       ├── ResilientAgentDesk.tsx        # NEPA heartbeat failover & 6-field AI context cards
│       └── PiiNdpaVault.tsx              # NDPA 2023 PII redaction tester & SHA-256 consent ledger
├── server.ts                             # Express + Vite dev gateway, /api/v1 SSE & HTTP proxy + offline fallback
├── backend/                              # Python FastAPI Modular Monolith
│   ├── app/
│   │   ├── main.py                       # FastAPI entrypoint, lifespan, CORS, route composition
│   │   ├── core/                         # Core Infrastructure (Config, Async SQLAlchemy RLS, Redis ARQ)
│   │   ├── adapters/                     # Hexagonal Port/Adapter external rails & registry
│   │   │   ├── base.py                   # Port interfaces (PaymentGatewayPort, WhatsAppBSPPort, LLMProviderPort)
│   │   │   ├── registry.py               # Declarative PROVIDER_REGISTRY adapter resolution
│   │   │   ├── whatsapp_dtos.py          # Provider-agnostic WhatsApp DTO schemas
│   │   │   ├── providers/                # Single-responsibility BSP adapters (meta, termii, twilio, dialog360)
│   │   │   ├── moniepoint.py             # Moniepoint MFB adapter + MockMoniepointAdapter
│   │   │   ├── custom_classifier.py      # ONNX Runtime / HuggingFace adapter
│   │   │   └── llm.py                    # Google Gemini 3.7 Flash adapter + MockLLMAdapter
│   │   ├── sandbox/                      # Isolated Local BSP Sandbox & Fault Injection Control Plane
│   │   │   ├── router.py                 # Thin HTTP/SSE endpoints (/api/v1/sandbox/*)
│   │   │   ├── service.py                # Sandbox orchestration, tenant seeding & webhook synthesis
│   │   │   ├── state.py                  # In-memory state, fault profiles, 24h session clock & SSE pub/sub
│   │   │   ├── adapter.py                # LocalSandboxBSPAdapter with chaos fault simulation
│   │   │   └── schemas.py                # Pydantic request/response schemas for the sandbox API
│   │   └── contexts/                     # 5 Enterprise Bounded Contexts + Core
│   │       ├── core/                     # Tenant infrastructure, merchants, users, RBAC
│   │       ├── ingress/                  # 3-Stage Cascading NLU Pipeline, Webhooks (<25ms ACK), AI Wallet
│   │       ├── ledger/                   # Anti-Ghosting carts, Virtual NUBANs, 4-Leg Double-Entry accounting
│   │       ├── reservations/             # Atomic slots, PostgreSQL GiST range locks, 10-min hold releaser
│   │       ├── desk/                     # Live agent NEPA heartbeat telemetry (<60s failover), Context Cards
│   │       └── compliance/               # NDPA 2023 SHA-256 Chained Consent Ledger, Ephemeral PII Token Vault
│   └── tests/                            # Pytest asynchronous domain & sandbox test suite
└── docker-compose.yml                    # Multi-container orchestration (Postgres 16, Redis 7, API, Worker)
```

---

## 2. Sandbox Frontend & Interactive Workbench

The React 19 frontend provides a 7-tab interactive engineering workbench for testing end-to-end conversational commerce flows, multi-provider webhooks, and chaos scenarios locally:

1. **WhatsApp Phone Simulator (`WhatsAppPhoneSimulator.tsx`)**
   - **High-Fidelity WhatsApp UI**: Supports text, Nigerian Pidgin presets, interactive reply buttons, bottom-sheet list drawers (`InteractiveListDrawer`), product carousels, voice note passthrough (`audio`), delivery location pins (`location`), and inline Moniepoint Virtual NUBAN settlement cards.
   - **Multi-Tenant & Multi-BSP Switching (`SimulatorControlBar`)**: Switch seamlessly between seeded Nigerian SME merchants (*Alaba Agro*, *Lekki Glow*, *Horizon Tech*) and BSP providers (`sandbox`, `meta`, `termii`, `twilio`, `360dialog`).
   - **Chaos & Edge-Case Fault Injection (`FaultInjectionPanel`)**: Toggle rate-limit `429`, upstream `500`, delivery failure statuses, HMAC signature corruption, duplicate webhook replay, 24-hour customer service window expiration (`+25h` clock offset + template-only enforcement), and 3-message rapid burst debouncing.
   - **Live NLU & Frame Inspector (`NluFrameInspectorPanel`)**: Toggle Stage 1 (Fast-Path), Stage 2 (Custom Model), and Stage 3 (Gemini LLM) at runtime, adjust confidence thresholds, and inspect the active multi-turn negotiation frame (`bound_slots`, `missing_slots`, `turn_count`).
2. **Webhook Inspector (`WebhookInspector.tsx`)**
   - Live stream of inbound/outbound provider webhooks with `<25ms` ACK latency metrics, HMAC verification badges, raw JSON payload inspection, and 1-click synthetic webhook triggers.
3. **NLU Intent Matrix (`NluIntentMatrix.tsx`)**
   - Real-time lead qualification matrix (`HOT` / `WARM` / `COLD`), Nigerian Pidgin & commercial slang detection, entity extraction viewer, and interactive NLU classification tester.
4. **Anti-Ghosting Ledger (`AntiGhostingLedger.tsx`)**
   - Tracks provisional shopping carts awaiting bank transfer, dedicated virtual NUBAN holds, 1-click NIBSS settlement simulation, and a 4-leg double-entry accounting validator (`Assets == Liabilities + Equity`).
5. **Atomic Reservation Grid (`AtomicReservationGrid.tsx`)**
   - Visualizes PostgreSQL GiST range-locked appointment slots (`AVAILABLE`, `HELD_PENDING_PAYMENT`, `CONFIRMED`) with live 10-minute hold expiration countdowns.
6. **Resilient Agent Desk (`ResilientAgentDesk.tsx`)**
   - Simulates human agent broadband/power (NEPA) dropouts (`ONLINE` vs `OFFLINE_NEPA`) and generates 6-field AI handoff context cards so agents never repeat customer questions.
7. **PII & NDPA Vault (`PiiNdpaVault.tsx`)**
   - Interactive Nigerian PII redaction tester (scrubbing 11-digit BVN, 11-digit NIN, 10-digit NUBAN, and 16-digit Card PANs prior to LLM escalation) alongside an immutable SHA-256 chained consent ledger (`STOP` / `UNSUBSCRIBE` revocation).

### Frontend Engineering Patterns
- **Typed API Client + TanStack Query**: All HTTP requests flow through `src/lib/apiClient.ts` and are consumed via `src/hooks/useSandboxApi.ts` (`useSandboxStateQuery`, `useSandboxInboundMutation`, `useSandboxBurstMutation`, etc.) with automatic cache invalidation.
- **Real-Time Server-Sent Events (SSE)**: `src/hooks/useSandboxStream.ts` subscribes to `/api/v1/sandbox/stream` for instant updates of outbound bot messages, webhook logs, NLU traces, and runtime controller changes.
- **Dual-Mode Gateway (`server.ts`)**: The Express + Vite server proxies `/api/v1/*` and SSE streams directly to the Python FastAPI backend (`PYTHON_API_URL`, default `http://localhost:8001` or `http://localhost:8000`), and automatically falls back to built-in Express simulation routes (`/api/*`) if the Python backend is offline.

---

## 3. 3-Stage Cascading Hybrid NLU Pipeline

Inbound customer messages pass through a 3-tier sequential cascading pipeline with dual confidence escalation gates and runtime-adjustable controllers:

```text
[Inbound WhatsApp Message]
       │
       ▼
[Compliance PII Sanitizer (BVN / NIN / NUBAN / PAN Redaction)]
       │
       ▼
[Stage 1: Fast-Path Router (pg_trgm, regex & Negotiation Frame)] ──(Confidence >= 0.90)──► [Instant Response: 0 tokens, ~2ms]
       │ (Confidence < 0.90)
       ▼
[Stage 2: Custom Local Model (HuggingFace/ONNX)] ────────────────(Confidence >= 0.75)──► [Template Response: 0 tokens, ~20ms]
       │ (Confidence < 0.75)
       ▼
[Stage 3: Gemini 3.7 Flash Escalation] ──────────────────────────(AI Wallet Debit)─────► [LLM Synthesis: ~400 tokens, ~380ms]
       │ (If LLM Disabled / Offline)
       ▼
[Graceful Fallback: Human Agent Desk Handoff]
```

### Environment Configuration

#### Frontend (`.env` / Vite `import.meta.env`)
Configure optional overrides in the root `.env` file (defaults are provided in `src/config/env.ts`):
```bash
# Express reverse-proxy target for the Python FastAPI server
PYTHON_API_URL=http://localhost:8000
GEMINI_API_KEY=your_gemini_api_key

# Optional Vite Sandbox Frontend overrides
VITE_API_V1_BASE=/api/v1
VITE_SANDBOX_STREAM_URL=/api/v1/sandbox/stream
VITE_SANDBOX_PROVIDER=sandbox
VITE_SANDBOX_PHONE_NUMBER_ID=meta_phone_alaba_agro
VITE_SANDBOX_CUSTOMER_PHONE=2348031234567
VITE_SANDBOX_CUSTOMER_DISPLAY_PHONE=+2348031234567
VITE_SANDBOX_CUSTOMER_NAME="Tunde Adeleke"
```

#### Backend (`backend/.env`)
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

## 4. Quickstart

### Option A: Run the Sandbox Frontend + Gateway
Install Node dependencies and launch the Vite + Express development server on `http://localhost:3000`:

```bash
# 1. Install frontend dependencies
npm install

# 2. Start the Sandbox Frontend & Express Gateway (port 3000)
npm run dev
```
> **Note:** `npm run dev` works standalone out-of-the-box using the Express fallback engine and automatically upgrades to full Python FastAPI sandbox state & SSE streaming when the backend is running.

### Option B: Run the Backend Stack with Docker Compose
Launch PostgreSQL 16, Redis 7, the FastAPI server, and the ARQ worker:

```bash
docker compose up --build
```
This provisions:
1. `bsp_postgres`: PostgreSQL 16 Alpine with `001_enterprise_schema.sql` on port `5432`.
2. `bsp_redis`: Redis 7 Alpine for the ARQ job queue on port `6379`.
3. `bsp_api`: FastAPI application with hot-reloading on `http://localhost:8000`.
4. `bsp_worker`: ARQ background worker for asynchronous webhook scoring and hold expiration crons.

### Option C: Local Backend Setup (Without Docker)

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

## 5. Verification & Test Suite

```bash
# Type-check the TypeScript Sandbox Frontend
npm run lint

# Run the Python FastAPI domain & sandbox test suite
cd backend
pytest -v
```

---

## 6. Interactive UI & API Endpoints

- **Sandbox Frontend Workbench**: `http://localhost:3000`
- **Interactive Swagger UI (FastAPI)**: `http://localhost:8000/docs`
- **ReDoc Explorer (FastAPI)**: `http://localhost:8000/redoc`
- **Sandbox Control Plane State**: `http://localhost:8000/api/v1/sandbox/state`
- **Sandbox Real-Time SSE Stream**: `http://localhost:8000/api/v1/sandbox/stream`
- **System Health Check**: `http://localhost:8000/api/health`
