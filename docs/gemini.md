# MeetWise — Ngữ Cảnh Dự Án cho Gemini AI

> **Phiên bản tài liệu:** v2.0 | **Cập nhật lần cuối:** 2026-05-24
> **Tác giả:** Đoàn Hoàng Việt (Việt Gamer)

---

## 1. Tổng Quan Dự Án

**MeetWise** là nền tảng SaaS AI giúp doanh nghiệp **đánh giá mức độ sẵn sàng cho cuộc họp** trước khi họp diễn ra. Hệ thống tự động phân tích điều kiện, thu thập dữ liệu thực tế và đưa ra quyết định `READY` hoặc `RESCHEDULED` kèm lý do cụ thể.

### Vấn đề giải quyết

- Các cuộc họp diễn ra khi chưa đủ điều kiện (tài liệu chưa xong, người chủ chốt bận)
- Mất thời gian nhân viên vào những cuộc họp vô bổ
- Không có hệ thống tự động kiểm tra sẵn sàng trước khi lịch họp đến

### Giải pháp

```
Điều kiện tự nhiên (tiếng Việt)
         ↓  LLM Parse (Gemini)
   Logic Expression
         ↓  Z3 SMT Solver
  Kết quả hình thức (READY/RESCHEDULED)
         ↓  Action Engine
   Thông báo + Đề xuất lịch mới
```

---

## 2. Kiến Trúc Hệ Thống (Neuro-Symbolic)

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js 14)                   │
│  Landing → Auth → Dashboard → Meetings → AI Evaluation UI   │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS / JWT
┌──────────────────────▼──────────────────────────────────────┐
│                   FastAPI Backend                            │
│  ┌─────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │  Auth/CRUD  │  │  AI Engine     │  │  Infrastructure  │  │
│  │  (Supabase) │  │  (LangGraph)   │  │  (Rate Limit,    │  │
│  │  api/v1/    │  │  agent/graph   │  │   Idempotency,   │  │
│  │  auth.py    │  │     ↓          │  │   Metrics, Trace)│  │
│  │  users.py   │  │  parse_input   │  └──────────────────┘  │
│  │  meeting_   │  │     ↓          │                        │
│  │  crud.py    │  │  fetch_facts   │                        │
│  └─────────────┘  │     ↓          │                        │
│                   │  verify_logic  │                        │
│                   │  (Z3 Solver)   │                        │
│                   │     ↓          │                        │
│                   │  decide_action │                        │
│                   └────────────────┘                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Supabase       Google           Resend
 (PostgreSQL      Workspace        (Email)
  + Auth)        (Calendar,
                  Chat, Drive)
```

### Nguyên tắc Neuro-Symbolic

- **Neural (LLM):** Gemini Flash parse ngôn ngữ tự nhiên → logic expression
- **Symbolic (Z3):** Theorem prover verify logic expression với facts → kết quả tất định, không hallucinate
- **Fallback:** Khi LLM không có/bị lỗi → deterministic parser tiếng Việt thay thế → không bao giờ crash

---

## 3. Cấu Trúc Thư Mục Đầy Đủ

```
meetwise-backend/
│
├── main.py                      # ✅ FastAPI app factory (351 dòng)
│   └── create_app()             #    Lifespan, CORS, exception handlers, routes
│
├── agent/                       # ✅ LangGraph AI Pipeline (CORE — KHÔNG SỬA)
│   ├── __init__.py
│   ├── graph.py                 #    StateGraph: START→parse→fetch→verify→decide→END
│   ├── nodes.py                 #    4 node functions (30KB, chứa toàn bộ AI logic)
│   ├── state.py                 #    MeetingState TypedDict (immutable)
│   └── tools.py                 #    LangGraph tools (Google Workspace, calculator)
│
├── solver/                      # ✅ Z3 SMT Solver (CORE — KHÔNG SỬA)
│   ├── __init__.py
│   ├── parser.py                #    Recursive descent parser → ConditionNode AST
│   ├── z3_engine.py             #    Z3 verify logic + unsat_core extraction
│   └── fallback_parser.py       #    Deterministic Vietnamese parser (khi LLM OFF/fail)
│
├── api/v1/                      # API Endpoints
│   ├── __init__.py
│   ├── meetings.py              # ✅ POST /v1/meetings/evaluate (420 dòng, KHÔNG SỬA)
│   ├── auth.py                  # 🆕 Auth endpoints (đăng ký, đăng nhập, OAuth)
│   ├── users.py                 # 🆕 User management
│   ├── meeting_crud.py          # 🆕 Meeting CRUD
│   ├── dashboard.py             # 🆕 Dashboard stats
│   └── notifications.py        # 🆕 Notifications
│
├── models/                      # 🆕 Database Models (Supabase/PostgreSQL)
│   ├── __init__.py
│   ├── user.py                  #    User, UserProfile
│   ├── meeting.py               #    Meeting (CRUD data, khác với AI evaluation)
│   ├── document.py              #    MeetingDocument
│   ├── evaluation_record.py     #    EvaluationRecord (lịch sử AI đánh giá)
│   ├── notification.py          #    Notification
│   └── team.py                  #    Team, TeamMember
│
├── services/                    # Business Logic
│   ├── __init__.py
│   ├── action_service.py        # ✅ Action execution (NOTIFY, RESCHEDULE)
│   ├── evaluate_service.py      # ✅ Gọi LangGraph pipeline
│   ├── idempotency.py           # ✅ Cache idempotency (5 phút TTL)
│   ├── rate_limiter.py          # ✅ Rate limiter (60 req/60s)
│   ├── sanitizer.py             # ✅ Input sanitization
│   ├── auth_service.py          # 🆕 Auth logic (Supabase JWT)
│   ├── user_service.py          # 🆕 User CRUD
│   ├── meeting_crud_service.py  # 🆕 Meeting CRUD business logic
│   ├── notification_service.py  # 🆕 Notification logic
│   └── email_service.py         # 🆕 Email via Resend
│
├── integrations/                # External Service Clients
│   ├── google_workspace.py      # ✅ Mock/Real Google APIs
│   ├── supabase_client.py       # 🆕 Supabase PostgreSQL + Auth
│   └── resend_client.py         # 🆕 Resend email API
│
├── middleware/                  # 🆕 FastAPI Middleware
│   ├── __init__.py
│   └── auth_middleware.py       #    JWT validation (python-jose + Supabase secret)
│
├── schemas/                     # Pydantic Models (API Contract)
│   ├── __init__.py
│   ├── request.py               # ✅ EvaluateRequest (LOCKED — frontend depends)
│   └── response.py              # ✅ EvaluateResponse, ErrorResponse (LOCKED)
│
├── core/                        # Infrastructure
│   ├── __init__.py
│   ├── config.py                # ✅ Settings (pydantic-settings, zero-setup)
│   ├── logging.py               # ✅ Structured JSON logging
│   ├── metrics.py               # ✅ In-memory metrics (latency, counts)
│   └── trace.py                 # ✅ ContextVar trace ID (thread-safe)
│
├── storage/                     # Data Layer
│   ├── __init__.py
│   ├── firestore_client.py      # ✅ Firestore client (lifecycle status)
│   └── mock_db.py               # ✅ In-memory mock (khi USE_FIREBASE=false)
│
├── tests/                       # Test Suite
│   ├── __init__.py
│   ├── test_api.py              # ✅ 13+ integration tests cho /evaluate
│   ├── test_solver.py           # ✅ Z3 engine tests
│   ├── test_fallback_parser.py  # ✅ Vietnamese parser tests
│   └── test_actions.py          # ✅ Action service tests
│
├── docs/                        # Documentation (tiếng Việt)
│   ├── (4 files markdown)
│
├── frontend/                    # 🆕 Next.js 14 App
│   └── (xem phần Frontend bên dưới)
│
├── main.py
├── requirements.txt
├── Dockerfile                   # Cloud Run ready (python:3.11-slim)
├── docker-compose.yml           # Local dev
├── pytest.ini
├── .env.example
├── .gitignore
├── gemini.md                    # File này
├── claude.md                    # Context cho Claude AI
└── README.md
```

**Chú thích:** ✅ = Đã có, hoạt động tốt | 🆕 = Cần tạo mới

---

## 4. API Endpoints

### Backend hiện tại (✅ Hoạt động)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/v1/meetings/evaluate` | **AI evaluation** — nhận rule + facts → trả READY/RESCHEDULED |
| `GET` | `/v1/meetings/{id}/status` | Lifecycle status của cuộc họp |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Service metrics (ẩn trong production) |
| `GET` | `/docs` | Swagger UI |

### Request/Response Contract (LOCKED — Frontend phụ thuộc)

```python
# POST /v1/meetings/evaluate
# Request:
{
  "meeting_id": "q1-kickoff-2024",      # str, ^[a-zA-Z0-9_-]+$, max 100
  "rule": "Slide cập nhật hoặc Sheet chốt số, bắt buộc Manager rảnh",  # str, max 2000
  "override_facts": {                    # Optional[Dict[str, bool]]
    "Slide_Done": false,
    "Sheet_Done": true,
    "Manager_Free": false
  }
}

# Response 200:
{
  "trace_id": "uuid",
  "meeting_id": "q1-kickoff-2024",
  "status": "READY" | "RESCHEDULED",
  "reason": "Giải thích lý do",
  "unsatisfied_conditions": ["Manager_Free"],
  "actions": [{"type": "NOTIFY", "target": "Manager", "status": "sent", ...}],
  "latency_ms": 45.2,
  "ai_reasoning": {
    "logic": "(Slide_Done OR Sheet_Done) AND Manager_Free",
    "evaluation": {"Slide_Done": false, "Sheet_Done": true, "Manager_Free": false},
    "decision_trace": ["Sheet_Done = TRUE → đã có chuẩn bị", ...]
  },
  "confidence": 1.0
}
```

### Backend mở rộng (🆕 Cần triển khai)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/v1/auth/dang-ky` | Đăng ký email/password |
| `POST` | `/v1/auth/dang-nhap` | Đăng nhập → JWT |
| `POST` | `/v1/auth/google` | Google OAuth2 |
| `POST` | `/v1/auth/lam-moi-token` | Refresh token |
| `GET` | `/v1/auth/thong-tin` | Profile user hiện tại |
| `POST` | `/v1/cuoc-hop` | Tạo cuộc họp mới |
| `GET` | `/v1/cuoc-hop` | Danh sách cuộc họp của user |
| `GET` | `/v1/cuoc-hop/{id}` | Chi tiết cuộc họp |
| `PUT` | `/v1/cuoc-hop/{id}` | Cập nhật cuộc họp |
| `DELETE` | `/v1/cuoc-hop/{id}` | Xóa cuộc họp |
| `POST` | `/v1/cuoc-hop/{id}/tai-lieu` | Gắn tài liệu |
| `POST` | `/v1/cuoc-hop/{id}/danh-gia` | Trigger AI evaluation |
| `GET` | `/v1/tong-quan` | Dashboard stats |
| `GET` | `/v1/tong-quan/bieu-do` | Chart data |
| `GET` | `/v1/thong-bao` | Danh sách thông báo |
| `PUT` | `/v1/thong-bao/{id}/da-doc` | Đánh dấu đã đọc |

---

## 5. Tech Stack

### Backend (Đã có — KHÔNG THAY ĐỔI)

| Library | Version | Mục đích |
|---------|---------|----------|
| `fastapi` | ≥0.111.0 | Web framework |
| `uvicorn[standard]` | ≥0.29.0 | ASGI server |
| `pydantic` | ≥2.7.0 | Validation |
| `pydantic-settings` | ≥2.2.0 | Config |
| `langgraph` | ≥0.1.19 | AI pipeline orchestration |
| `langchain-core` | ≥0.2.5 | LangChain foundation |
| `langchain-google-genai` | ≥1.0.6 | Gemini integration |
| `google-genai` | ≥0.7.0 | Google AI SDK |
| `z3-solver` | ≥4.12.0.0 | SMT theorem prover |
| `google-cloud-firestore` | ≥2.16.0 | Firestore storage |
| `httpx` | ≥0.27.0 | Async HTTP client |
| `python-json-logger` | ≥2.0.7 | Structured logging |

### Frontend (🆕 Cần cài)

| Library | Mục đích |
|---------|----------|
| Next.js 14 (App Router) | React framework |
| TailwindCSS | Utility CSS |
| Shadcn UI | Component library |
| Zustand | State management |
| React Query (TanStack) | Data fetching |
| Recharts | Dashboard charts |
| React Hook Form | Form handling |
| Zod | Client-side validation |

### External Services

| Service | Mục đích | Free tier |
|---------|----------|-----------|
| Supabase | PostgreSQL + Auth | 500MB, unlimited auth |
| Google Gemini API | LLM (optional) | 15 req/min, 1M tokens/ngày |
| Resend | Email | 100 emails/ngày |
| Vercel | Frontend deploy | Hobby free |
| Render | Backend deploy | Free tier |

---

## 6. Zero-Setup Mode (Quan Trọng)

Backend có thể chạy **hoàn toàn không cần API key**:

```bash
# .env mặc định (hoặc không cần .env)
USE_LLM=false              # → Dùng fallback parser deterministic
USE_FIREBASE=false         # → Dùng in-memory dict storage
USE_GOOGLE_SERVICES=false  # → Dùng mock Google Workspace
```

**Khi bật từng service:**
```bash
USE_LLM=true              # Cần: GEMINI_API_KEY
USE_FIREBASE=true         # Cần: FIREBASE_PROJECT_ID + credentials
USE_GOOGLE_SERVICES=true  # Cần: GOOGLE_SERVICE_ACCOUNT_JSON
```

---

## 7. LangGraph Pipeline (4 Bước)

```
START
  │
  ▼
parse_input_node          # LLM (hoặc fallback) parse rule tiếng Việt
  │  → parsed_ast: ConditionNode
  │  → logic_expression: "(Slide_Done OR Sheet_Done) AND Manager_Free"
  │  → parse_source: 'llm' | 'fallback' | 'skip_llm'
  │  ──(error)──→ END
  │
  ▼
fetch_facts_node           # Thu thập giá trị thực tế của các điều kiện
  │  → fetched_facts: {"Slide_Done": false, "Sheet_Done": true, ...}
  │  → Ưu tiên: override_facts > Google APIs > mock values
  │  ──(error)──→ END
  │
  ▼
verify_logic_node          # Z3 SMT Solver verify
  │  → verify_result: VerifyResult
  │  → is_satisfiable: bool
  │  → unsat_core: ["Manager_Free"]  ← điều kiện chặn
  │  ──(error)──→ END
  │
  ▼
decide_action_node         # Quyết định + thực thi actions
  │  → final_status: "READY" | "RESCHEDULED"
  │  → executed_actions: [NOTIFY, RESCHEDULE]
  │
  ▼
END
```

**Timeout:** 10s toàn pipeline | 5s mỗi step

---

## 8. State Management (MeetingState)

`agent/state.py` định nghĩa `MeetingState` TypedDict — **immutable**, mỗi node return dict mới:

| Field | Type | Bởi node |
|-------|------|----------|
| `trace_id` | `str` | parse_input |
| `meeting_id` | `str` | parse_input |
| `raw_rule` | `str` | parse_input |
| `parsed_ast` | `ConditionNode` | parse_input |
| `logic_expression` | `str` | parse_input |
| `parse_source` | `str` | parse_input |
| `fetched_facts` | `Dict[str, bool]` | fetch_facts |
| `verify_result` | `VerifyResult` | verify_logic |
| `final_status` | `"READY"\|"RESCHEDULED"` | decide_action |
| `unsatisfied_conditions` | `List[str]` | decide_action |
| `executed_actions` | `List[Dict]` | decide_action |
| `error_code` | `str` | bất kỳ node |
| `step_latencies` | `Dict[str, float]` | tất cả nodes |

---

## 9. Schema Response (LOCKED — Frontend Phụ Thuộc)

> ⚠️ **KHÔNG thay đổi** `schemas/request.py` và `schemas/response.py` mà không cập nhật frontend.

**EvaluateResponse fields:**
- `trace_id`: UUID debug
- `meeting_id`: ID cuộc họp
- `status`: `"READY"` hoặc `"RESCHEDULED"`
- `reason`: Giải thích tiếng Việt
- `unsatisfied_conditions`: List điều kiện chưa thỏa
- `actions`: List ActionResult (NOTIFY/RESCHEDULE)
- `latency_ms`: Thời gian xử lý
- `ai_reasoning.logic`: Logic expression hình thức
- `ai_reasoning.evaluation`: Dict[str, bool] từng điều kiện
- `ai_reasoning.decision_trace`: Diễn giải từng bước
- `confidence`: Luôn là 1.0 (Z3 tất định)

---

## 10. Conventions & Patterns

### Naming Conventions

```python
# Python (backend)
snake_case          # biến, hàm, file, module
PascalCase          # class, Pydantic model, TypedDict
UPPER_SNAKE_CASE    # hằng số, error codes

# TypeScript (frontend)
camelCase           # biến, hàm
PascalCase          # component, interface, type
UPPER_SNAKE_CASE    # hằng số

# Database (Supabase)
snake_case          # tên bảng, cột (users, meeting_id, created_at)

# API Endpoints
kebab-case          # URL paths (/cuoc-hop, /tong-quan)
```

### Error Handling Pattern

```python
# Backend: Global exception handler → ErrorResponse
{
  "error": {"code": "VALIDATION_ERROR", "message": "..."},
  "trace_id": "uuid"
}

# Frontend: Toast notification (Shadcn)
toast.error("Không thể tạo cuộc họp. Vui lòng thử lại.")
```

### Async Pattern (FastAPI)

```python
# Tất cả endpoints đều async
@router.post("/evaluate")
async def evaluate_meeting(request: EvaluateRequest) -> EvaluateResponse:
    result = await evaluate_service.run(request)  # await everywhere
    return result
```

### Auth Pattern

```
Frontend → [JWT token in Authorization header]
  → FastAPI auth_middleware → verify với Supabase JWT secret
  → inject user_id vào request state
  → endpoint handler lấy current_user từ request.state.user
```

---

## 11. Database Schema (Supabase — Cần Tạo)

```sql
-- users (quản lý bởi Supabase Auth)
-- Chỉ cần thêm profile table:
CREATE TABLE user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  full_name TEXT,
  organization TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- meetings (CRUD data — tách biệt với AI evaluation)
CREATE TABLE meetings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES auth.users(id),
  title TEXT NOT NULL,
  description TEXT,
  scheduled_at TIMESTAMPTZ NOT NULL,
  location TEXT,
  rule TEXT NOT NULL,           -- điều kiện họp (gửi cho AI)
  status TEXT DEFAULT 'pending', -- pending | evaluated | ready | rescheduled
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- meeting_documents
CREATE TABLE meeting_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  type TEXT,  -- slide | sheet | report | other
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- evaluation_records (lịch sử AI đánh giá)
CREATE TABLE evaluation_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  trace_id TEXT NOT NULL,       -- từ AI engine
  ai_status TEXT NOT NULL,      -- READY | RESCHEDULED
  reason TEXT,
  unsatisfied_conditions TEXT[], -- array of condition names
  ai_reasoning JSONB,           -- full AIReasoning object
  latency_ms FLOAT,
  evaluated_at TIMESTAMPTZ DEFAULT NOW()
);

-- notifications
CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  meeting_id UUID REFERENCES meetings(id),
  type TEXT NOT NULL,           -- evaluation_complete | meeting_rescheduled | reminder
  title TEXT NOT NULL,
  body TEXT,
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 12. Hướng Dẫn Cho Gemini

### Khi đọc code backend

1. **Core engine không được sửa:** `agent/`, `solver/` — chỉ đọc để hiểu
2. **Mọi module mới** phải gọi AI engine qua `evaluate_service.py`, không gọi thẳng vào `agent/graph.py`
3. `schemas/response.py` là **contract cứng** — đừng thêm/xóa field

### Khi tạo API endpoint mới

```python
# Pattern chuẩn
from fastapi import APIRouter, Depends, HTTPException, status
from middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/v1", tags=["feature"])

@router.get("/endpoint")
async def handler(
    current_user = Depends(get_current_user),  # Auth inject
) -> ResponseModel:
    try:
        result = await some_service.do_something()
        return result
    except SomeException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
```

### Khi tạo component frontend

```typescript
// Pattern chuẩn (Next.js App Router)
"use client";

import { useState } from "react";
import { toast } from "sonner";  // Shadcn toast
import { useMutation } from "@tanstack/react-query";

export function ComponentName() {
  const mutation = useMutation({
    mutationFn: apiFunction,
    onSuccess: () => toast.success("Thành công!"),
    onError: (err) => toast.error(`Lỗi: ${err.message}`),
  });

  return <div>...</div>;
}
```

---

## 13. Luồng Phát Triển Hiện Tại

### Đã hoàn thành (✅)
- Backend AI Engine (LangGraph + Z3 + FastAPI)
- 13+ integration tests
- Docker + docker-compose

### Đang triển khai (🔄)
- Phase 1: Documentation (`gemini.md`, `claude.md`, `README.md`)
- Phase 2: Backend mở rộng (Auth, Models, CRUD)
- Phase 3: Frontend (Next.js 14)

### Branch hiện tại
```
feature/01-project-docs  ← đang ở đây
```

---

*Tài liệu này được tối ưu cho Gemini 1.5 Flash/Pro với context window lớn. Cập nhật mỗi khi có thay đổi kiến trúc quan trọng.*
