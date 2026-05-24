<div align="center">

# 🤝 MeetWise

**Nền tảng SaaS AI đánh giá mức độ sẵn sàng cuộc họp**

*Tránh các cuộc họp vô bổ, tốn thời gian — trước khi chúng xảy ra*

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.1-FF6B6B?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Z3](https://img.shields.io/badge/Z3_Solver-4.12-764ABC?style=for-the-badge)](https://github.com/Z3Prover/z3)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

[📖 Tài liệu API](http://localhost:8000/docs) · [🚀 Demo Live](#) · [🐛 Báo lỗi](https://github.com/VietGamer-UIT/meetwise-backend/issues) · [💡 Đề xuất tính năng](https://github.com/VietGamer-UIT/meetwise-backend/issues)

</div>

---

## 📋 Mục Lục

- [Giới thiệu](#-giới-thiệu)
- [Tính năng](#-tính-năng)
- [Kiến trúc](#-kiến-trúc)
- [Cấu trúc dự án](#-cấu-trúc-dự-án)
- [Bắt đầu nhanh](#-bắt-đầu-nhanh)
  - [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
  - [Chạy với Docker](#chạy-với-docker)
  - [Chạy thủ công](#chạy-thủ-công-backend)
  - [Chạy Frontend](#chạy-frontend)
- [Cấu hình](#-cấu-hình)
- [API Reference](#-api-reference)
- [Testing](#-testing)
- [Tech Stack](#-tech-stack)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🎯 Giới Thiệu

MeetWise là công cụ AI giúp bạn trả lời câu hỏi: **"Cuộc họp này có nên diễn ra không?"**

Thay vì họp rồi mới phát hiện thiếu tài liệu, thiếu người quyết định, hay thông tin chưa sẵn sàng — MeetWise đánh giá **trước** và tự động thông báo nếu cần dời lịch.

### Ví dụ thực tế

```
Điều kiện: "Slide cập nhật hoặc Sheet chốt số, bắt buộc Manager rảnh"

Thực tế:   Slide_Done = ❌  |  Sheet_Done = ✅  |  Manager_Free = ❌

Kết quả:   🔴 RESCHEDULED
           Lý do: Manager_Free chưa thỏa mãn
           Hành động: Đã thông báo Manager + Đề xuất lịch mới
```

---

## ✨ Tính Năng

| Tính năng | Mô tả |
|-----------|-------|
| 🧠 **Neuro-Symbolic AI** | LLM parse ngôn ngữ tự nhiên + Z3 Theorem Prover verify logic |
| 🔄 **Zero-Hallucination** | Z3 SMT Solver đảm bảo kết quả tất định, không đoán mò |
| 🌐 **Tiếng Việt native** | Hỗ trợ điều kiện viết bằng tiếng Việt tự nhiên |
| 🔌 **Zero-Setup** | Chạy ngay không cần API key hay config phức tạp |
| 🛡️ **Production-grade** | Rate limiting, idempotency, distributed tracing, metrics |
| 🔗 **Google Workspace** | Tích hợp Calendar, Chat, Drive, Sheets (mock hoặc thật) |
| 👤 **Auth & CRUD** | Quản lý người dùng, cuộc họp, tài liệu qua Supabase |
| 📊 **Dashboard Analytics** | Biểu đồ xu hướng, thống kê sẵn sàng họp |
| 📧 **Email Notifications** | Thông báo tự động qua Resend |

---

## 🏗️ Kiến Trúc

```
┌─────────────────────────────────────────────────────┐
│              Next.js 14 Frontend                     │
│   Landing → Auth → Dashboard → Meetings → Evaluation│
└──────────────────────┬──────────────────────────────┘
                       │ JWT / HTTPS
┌──────────────────────▼──────────────────────────────┐
│                 FastAPI Backend                      │
│                                                      │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  Auth + CRUD │    │    Neuro-Symbolic AI      │   │
│  │  (Supabase)  │    │    Engine (CORE)          │   │
│  │              │    │                           │   │
│  │  /auth       │    │  LangGraph Pipeline:      │   │
│  │  /users      │    │  parse → fetch → verify   │   │
│  │  /cuoc-hop   │    │         → decide          │   │
│  │  /tong-quan  │    │              ↓            │   │
│  │  /thong-bao  │    │    Z3 SMT Solver          │   │
│  └──────────────┘    └──────────────────────────┘   │
└──────────────────────────────────────────────────────┘
         │                    │
    Supabase             Google APIs
 (PostgreSQL + Auth)   (Calendar, Chat,
                        Drive, Sheets)
```

### Luồng AI Evaluation

```
User nhập rule (tiếng Việt)
        ↓
   LLM (Gemini)         ← optional, có fallback
   parse → logic
        ↓
  Z3 SMT Solver         ← tất định, không hallucinate
  verify logic
        ↓
   READY / RESCHEDULED
        ↓
  Actions (nếu RESCHEDULED)
  • Gửi thông báo
  • Đề xuất lịch mới
```

---

## 📁 Cấu Trúc Dự Án

```
meetwise-backend/
│
├── 📄 main.py                   # FastAPI app factory, lifespan, exception handlers
├── 📄 requirements.txt          # Python dependencies
├── 📄 Dockerfile                # Cloud Run ready (python:3.11-slim)
├── 📄 docker-compose.yml        # Local development
├── 📄 pytest.ini                # Test configuration
├── 📄 .env.example              # Environment variables template
├── 📄 gemini.md                 # Context cho Gemini AI
├── 📄 claude.md                 # Context cho Claude AI
│
├── 🤖 agent/                    # LangGraph AI Pipeline (CORE)
│   ├── graph.py                 # StateGraph: 4 nodes + conditional edges
│   ├── nodes.py                 # parse_input, fetch_facts, verify_logic, decide_action
│   ├── state.py                 # MeetingState TypedDict (immutable)
│   └── tools.py                 # Google Workspace tools
│
├── 🔢 solver/                   # Z3 Neuro-Symbolic Engine (CORE)
│   ├── parser.py                # Recursive descent parser → ConditionNode AST
│   ├── z3_engine.py             # Z3 verify + unsat_core extraction
│   └── fallback_parser.py       # Deterministic Vietnamese parser
│
├── 🌐 api/v1/                   # REST API Endpoints
│   ├── meetings.py              # POST /v1/meetings/evaluate (AI evaluation)
│   ├── auth.py                  # Auth: đăng ký, đăng nhập, OAuth
│   ├── users.py                 # User management
│   ├── meeting_crud.py          # Meeting CRUD
│   ├── dashboard.py             # Dashboard stats & charts
│   └── notifications.py        # Notifications
│
├── 🗄️ models/                   # Database Models (Supabase)
│   ├── user.py                  # User, UserProfile
│   ├── meeting.py               # Meeting (CRUD)
│   ├── document.py              # MeetingDocument
│   ├── evaluation_record.py     # AI evaluation history
│   ├── notification.py          # Notification
│   └── team.py                  # Team, TeamMember
│
├── ⚙️ services/                  # Business Logic Layer
│   ├── action_service.py        # NOTIFY + RESCHEDULE actions
│   ├── evaluate_service.py      # Gọi LangGraph pipeline
│   ├── idempotency.py           # Cache idempotency (5 phút TTL)
│   ├── rate_limiter.py          # Rate limiter (60 req/60s per IP)
│   ├── sanitizer.py             # Input sanitization
│   ├── auth_service.py          # Supabase auth logic
│   ├── user_service.py          # User CRUD
│   ├── meeting_crud_service.py  # Meeting CRUD business logic
│   ├── notification_service.py  # Notification logic
│   └── email_service.py         # Email via Resend
│
├── 🔌 integrations/             # External Service Clients
│   ├── google_workspace.py      # Mock/Real Google APIs
│   ├── supabase_client.py       # Supabase PostgreSQL + Auth
│   └── resend_client.py         # Resend email API
│
├── 🛡️ middleware/               # FastAPI Middleware
│   └── auth_middleware.py       # JWT validation (python-jose)
│
├── 📝 schemas/                  # Pydantic Models (API Contract)
│   ├── request.py               # EvaluateRequest (⚠️ LOCKED)
│   └── response.py              # EvaluateResponse, ErrorResponse (⚠️ LOCKED)
│
├── 🏗️ core/                     # Infrastructure
│   ├── config.py                # Settings (pydantic-settings, zero-setup)
│   ├── logging.py               # Structured JSON logging
│   ├── metrics.py               # In-memory metrics
│   └── trace.py                 # ContextVar trace ID (thread-safe)
│
├── 💾 storage/                  # Data Layer
│   ├── firestore_client.py      # Firestore (khi USE_FIREBASE=true)
│   └── mock_db.py               # In-memory mock
│
├── 🧪 tests/                    # Test Suite (13+ tests)
│   ├── test_api.py              # API integration tests
│   ├── test_solver.py           # Z3 engine tests
│   ├── test_fallback_parser.py  # Vietnamese parser tests
│   └── test_actions.py          # Action service tests
│
├── 📚 docs/                     # Documentation (tiếng Việt)
│
└── 🖥️ frontend/                 # Next.js 14 Frontend
    ├── src/app/                 # App Router pages
    ├── src/components/          # React components
    ├── src/lib/                 # Utilities, API client
    ├── src/hooks/               # Custom React hooks
    └── src/types/               # TypeScript types
```

---

## 🚀 Bắt Đầu Nhanh

### Yêu Cầu Hệ Thống

- **Python** 3.11+
- **Node.js** 18+
- **Docker** & **Docker Compose** (tùy chọn, khuyến nghị)
- **Git**

### Clone Repository

```bash
git clone https://github.com/VietGamer-UIT/meetwise-backend.git
cd meetwise-backend
```

---

### Chạy Với Docker (Khuyến Nghị)

Cách nhanh nhất — không cần cài Python hay Node.js:

```bash
# Copy file cấu hình mẫu
cp .env.example .env

# Khởi động toàn bộ stack
docker-compose up --build

# Chạy ở background
docker-compose up -d --build
```

Sau khi khởi động:
- **Backend API:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

---

### Chạy Thủ Công — Backend

**Bước 1: Tạo môi trường ảo**

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python -m venv .venv
source .venv/bin/activate
```

**Bước 2: Cài dependencies**

```bash
pip install -r requirements.txt
```

**Bước 3: Cấu hình môi trường**

```bash
cp .env.example .env
# Chỉnh sửa .env nếu cần (mặc định chạy được ngay không cần API key)
```

**Bước 4: Khởi động server**

```bash
# Development (auto-reload)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Hoặc
python main.py
```

**Bước 5: Kiểm tra**

```bash
# Health check
curl http://localhost:8000/health

# Test AI evaluation (zero-setup — không cần API key)
curl -X POST http://localhost:8000/v1/meetings/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "meeting_id": "test-001",
    "rule": "(Slide_Done OR Sheet_Done) AND Manager_Free",
    "override_facts": {
      "Slide_Done": false,
      "Sheet_Done": true,
      "Manager_Free": false
    }
  }'
```

---

### Chạy Frontend

```bash
cd frontend

# Cài dependencies
npm install

# Cấu hình môi trường
cp .env.example .env.local
# Chỉnh sửa NEXT_PUBLIC_API_URL và Supabase credentials

# Development server
npm run dev
```

Frontend chạy tại: http://localhost:3000

---

### Chạy Tests

```bash
# Backend tests
python -m pytest tests/ -v

# Chạy từng file
python -m pytest tests/test_api.py -v
python -m pytest tests/test_solver.py -v
python -m pytest tests/test_fallback_parser.py -v
python -m pytest tests/test_actions.py -v

# Frontend tests
cd frontend
npm run test
```

---

## ⚙️ Cấu Hình

### Backend Environment Variables

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `APP_ENV` | `development` | Môi trường (`development`/`production`) |
| `LOG_LEVEL` | `INFO` | Mức log (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| **Zero-Setup Switches** | | |
| `USE_LLM` | `false` | Bật Gemini LLM (cần `GEMINI_API_KEY`) |
| `USE_FIREBASE` | `false` | Bật Firestore (cần `FIREBASE_PROJECT_ID`) |
| `USE_GOOGLE_SERVICES` | `false` | Bật Google Workspace APIs |
| **AI/LLM** | | |
| `GEMINI_API_KEY` | `` | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Model LLM sử dụng |
| **Supabase** | | |
| `SUPABASE_URL` | `` | URL Supabase project |
| `SUPABASE_ANON_KEY` | `` | Anon key (public) |
| `SUPABASE_SERVICE_ROLE_KEY` | `` | Service role key (secret) |
| `SUPABASE_JWT_SECRET` | `` | JWT secret để verify token |
| **Email** | | |
| `RESEND_API_KEY` | `` | Resend API key |
| **Rate Limiting** | | |
| `RATE_LIMIT_MAX_REQUESTS` | `60` | Số request tối đa |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Cửa sổ thời gian (giây) |
| **CORS** | | |
| `CORS_ALLOWED_ORIGINS` | `*` | Origins cho phép (`,` phân cách) |

### Frontend Environment Variables

| Biến | Mô tả |
|------|-------|
| `NEXT_PUBLIC_API_URL` | URL backend API |
| `NEXT_PUBLIC_SUPABASE_URL` | URL Supabase project |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |

---

## 📡 API Reference

### AI Evaluation

#### `POST /v1/meetings/evaluate`

Đánh giá mức độ sẵn sàng của cuộc họp.

**Request Body:**
```json
{
  "meeting_id": "q1-kickoff-2024",
  "rule": "(Slide_Done OR Sheet_Done) AND Manager_Free",
  "override_facts": {
    "Slide_Done": false,
    "Sheet_Done": true,
    "Manager_Free": false
  }
}
```

**Response 200 — READY:**
```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "meeting_id": "q1-kickoff-2024",
  "status": "READY",
  "reason": "Tất cả điều kiện đã thỏa mãn. Cuộc họp có thể diễn ra.",
  "unsatisfied_conditions": [],
  "actions": [],
  "latency_ms": 23.5,
  "ai_reasoning": {
    "logic": "(Slide_Done OR Sheet_Done) AND Manager_Free",
    "evaluation": {"Slide_Done": true, "Sheet_Done": true, "Manager_Free": true},
    "decision_trace": ["Slide_Done = TRUE", "Manager_Free = TRUE", "Tất cả điều kiện thỏa mãn"]
  },
  "confidence": 1.0
}
```

**Response 200 — RESCHEDULED:**
```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "meeting_id": "q1-kickoff-2024",
  "status": "RESCHEDULED",
  "reason": "Điều kiện 'Manager_Free' chưa thỏa mãn. Cuộc họp cần được dời.",
  "unsatisfied_conditions": ["Manager_Free"],
  "actions": [
    {
      "type": "NOTIFY",
      "target": "Manager",
      "status": "sent",
      "message": "Cuộc họp Q1 Kickoff cần dời do Manager chưa rảnh."
    },
    {
      "type": "RESCHEDULE",
      "target": null,
      "status": "sent",
      "proposed_time": "2026-05-25T10:00:00"
    }
  ],
  "latency_ms": 45.2,
  "ai_reasoning": {
    "logic": "(Slide_Done OR Sheet_Done) AND Manager_Free",
    "evaluation": {"Slide_Done": false, "Sheet_Done": true, "Manager_Free": false},
    "decision_trace": ["Sheet_Done = TRUE → có chuẩn bị", "Manager_Free = FALSE → điều kiện chặn"]
  },
  "confidence": 1.0
}
```

### System

| Endpoint | Mô tả |
|----------|-------|
| `GET /health` | Health check |
| `GET /metrics` | Service metrics |
| `GET /docs` | Swagger UI |
| `GET /v1/meetings/{id}/status` | Lifecycle status cuộc họp |

### Error Codes

| Code | HTTP | Mô tả |
|------|------|-------|
| `VALIDATION_ERROR` | 400 | Request body không hợp lệ |
| `RATE_LIMIT_EXCEEDED` | 429 | Vượt rate limit (60 req/min) |
| `ALREADY_PROCESSING` | 409 | Request đang được xử lý (idempotency) |
| `TIMEOUT` | 408 | AI pipeline timeout (>10s) |
| `INTERNAL_ERROR` | 500 | Lỗi nội bộ |

---

## 🛠️ Tech Stack

### Backend

| Category | Technology |
|----------|-----------|
| **Web Framework** | FastAPI 0.111+ |
| **AI Orchestration** | LangGraph 0.1+ |
| **LLM** | Google Gemini 1.5 Flash (optional) |
| **Logic Engine** | Z3 Theorem Prover 4.12+ |
| **Database** | Supabase (PostgreSQL) |
| **Auth** | Supabase Auth (JWT) |
| **HTTP Client** | httpx (async) |
| **Validation** | Pydantic v2 |
| **Config** | pydantic-settings |
| **Logging** | python-json-logger |
| **Testing** | pytest + pytest-asyncio |
| **Container** | Docker (python:3.11-slim) |

### Frontend

| Category | Technology |
|----------|-----------|
| **Framework** | Next.js 14 (App Router) |
| **Styling** | TailwindCSS |
| **Components** | Shadcn UI |
| **State** | Zustand + React Query |
| **Forms** | React Hook Form + Zod |
| **Charts** | Recharts |
| **Auth** | Supabase Auth (SSR) |
| **HTTP** | fetch (native) |

### Infrastructure

| Category | Technology |
|----------|-----------|
| **Frontend Deploy** | Vercel (free) |
| **Backend Deploy** | Render / Google Cloud Run |
| **Database** | Supabase (500MB free) |
| **Email** | Resend (100 emails/ngày free) |
| **CI/CD** | GitHub Actions |

---

## 🤝 Contributing

Mọi đóng góp đều được hoan nghênh! Vui lòng:

1. **Fork** repository
2. **Tạo branch** từ `develop`: `git checkout -b feature/ten-tinh-nang`
3. **Commit** theo [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat(scope): mô tả ngắn
   fix(scope): mô tả lỗi
   test(scope): thêm tests
   docs(scope): cập nhật docs
   ```
4. **Push** và tạo **Pull Request** vào `develop`
5. Đợi review

### Coding Standards

- **Python:** PEP 8, type hints bắt buộc, async/await cho I/O
- **TypeScript:** strict mode, no `any`
- **Comments:** Tiếng Việt hoặc song ngữ
- **Tests:** Bắt buộc cho feature mới

---

## 📄 License

MIT License — xem [LICENSE](LICENSE) để biết thêm chi tiết.

---

<div align="center">

**Xây dựng bởi [Đoàn Hoàng Việt (Việt Gamer)](https://github.com/VietGamer-UIT)**

*Powered by FastAPI · LangGraph · Z3 Theorem Prover · Next.js · Supabase*

⭐ Star nếu dự án hữu ích với bạn!

</div>
