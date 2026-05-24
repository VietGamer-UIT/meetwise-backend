# MeetWise — Ngữ Cảnh Dự Án cho Claude AI

> **Phiên bản tài liệu:** v2.0 | **Cập nhật lần cuối:** 2026-05-24
> **Tác giả:** Đoàn Hoàng Việt (Việt Gamer)
> **Tối ưu cho:** Claude Sonnet/Opus (context window 200K tokens)

---

## System Prompt cho Claude

```
Bạn là Senior Fullstack Engineer đang làm việc trên dự án MeetWise — nền tảng SaaS AI
đánh giá mức độ sẵn sàng cuộc họp. Stack: FastAPI + LangGraph + Z3 (backend),
Next.js 14 + TailwindCSS + Shadcn UI (frontend), Supabase (database + auth).

Nguyên tắc tuyệt đối:
1. KHÔNG sửa các file trong agent/ và solver/ — đây là AI core engine đã hoạt động
2. KHÔNG thay đổi schemas/request.py và schemas/response.py — frontend phụ thuộc vào đây
3. Output FULL file, không dùng "# ... existing code ..."
4. UI text 100% tiếng Việt, code (biến/hàm/class) 100% tiếng Anh
5. Mọi FastAPI endpoint đều async, mọi DB call đều await
```

---

## 1. File Dependency Graph

```
main.py
├── api/v1/meetings.py           ← evaluate endpoint
│   ├── services/evaluate_service.py
│   │   └── agent/graph.py       ← LangGraph (CORE)
│   │       ├── agent/nodes.py   ← 4 pipeline nodes
│   │       ├── agent/state.py   ← MeetingState TypedDict
│   │       └── agent/tools.py   ← Google Workspace tools
│   ├── services/rate_limiter.py
│   ├── services/idempotency.py
│   ├── services/sanitizer.py
│   └── schemas/
│       ├── request.py           ← EvaluateRequest (LOCKED)
│       └── response.py          ← EvaluateResponse (LOCKED)
│
├── core/
│   ├── config.py                ← Settings singleton (pydantic-settings)
│   ├── logging.py               ← Structured JSON logger
│   ├── metrics.py               ← In-memory metrics counter
│   └── trace.py                 ← ContextVar trace ID
│
├── solver/                      ← Z3 Neuro-Symbolic (CORE)
│   ├── parser.py                ← Recursive descent → ConditionNode AST
│   ├── z3_engine.py             ← Z3 verify + unsat_core
│   └── fallback_parser.py       ← Deterministic Vietnamese parser
│
├── storage/
│   ├── firestore_client.py      ← Firestore (khi USE_FIREBASE=true)
│   └── mock_db.py               ← In-memory (khi USE_FIREBASE=false)
│
└── integrations/
    └── google_workspace.py      ← Mock/Real Google APIs

─── CẦN TẠO MỚI ───────────────────────────────────────────

api/v1/
├── auth.py                      ← phụ thuộc: middleware/auth_middleware.py
├── users.py                     ← phụ thuộc: services/user_service.py
├── meeting_crud.py              ← phụ thuộc: services/meeting_crud_service.py
│                                            + services/evaluate_service.py (AI)
├── dashboard.py                 ← phụ thuộc: storage/supabase (query)
└── notifications.py             ← phụ thuộc: services/notification_service.py

middleware/
└── auth_middleware.py           ← phụ thuộc: integrations/supabase_client.py
                                              + core/config.py (SUPABASE_JWT_SECRET)

services/ (mới)
├── auth_service.py              ← phụ thuộc: integrations/supabase_client.py
├── user_service.py              ← phụ thuộc: integrations/supabase_client.py
├── meeting_crud_service.py      ← phụ thuộc: integrations/supabase_client.py
├── notification_service.py      ← phụ thuộc: integrations/supabase_client.py
└── email_service.py             ← phụ thuộc: integrations/resend_client.py

integrations/ (mới)
├── supabase_client.py           ← supabase-py library
└── resend_client.py             ← httpx + Resend API

models/ (mới — Pydantic models cho DB)
├── user.py
├── meeting.py
├── document.py
├── evaluation_record.py
├── notification.py
└── team.py
```

---

## 2. Kiến Trúc Chi Tiết

### LangGraph Pipeline (KHÔNG SỬA)

```
START → parse_input_node → fetch_facts_node → verify_logic_node → decide_action_node → END
              ↓(error)           ↓(error)           ↓(error)
             END                END                END
```

**parse_input_node** (`agent/nodes.py`):
- Nếu `USE_LLM=true`: Gọi Gemini Flash để parse rule tiếng Việt → logic expression
- Nếu `USE_LLM=false`: Gọi `fallback_parser.py` (deterministic)
- Output: `logic_expression`, `parsed_ast`, `parse_source`

**fetch_facts_node** (`agent/nodes.py`):
- Ưu tiên: `override_facts` (từ request) > Google APIs > mock values
- Output: `fetched_facts: Dict[str, bool]`

**verify_logic_node** (`agent/nodes.py`):
- Gọi `z3_engine.verify(logic_expression, fetched_facts)`
- Output: `verify_result` chứa `is_satisfiable`, `unsat_core`

**decide_action_node** (`agent/nodes.py`):
- Nếu READY: không action
- Nếu RESCHEDULED: gọi `action_service` → NOTIFY + RESCHEDULE
- Output: `final_status`, `final_reason`, `executed_actions`

### Z3 Solver (KHÔNG SỬA)

```python
# Ví dụ verify
from solver.z3_engine import z3_engine

result = z3_engine.verify(
    logic_expression="(Slide_Done OR Sheet_Done) AND Manager_Free",
    facts={"Slide_Done": False, "Sheet_Done": True, "Manager_Free": False}
)
# result.is_satisfiable = False
# result.unsat_core = ["Manager_Free"]
```

### Auth Flow (Supabase JWT)

```
[Client] → POST /v1/auth/dang-nhap → [Supabase Auth]
                                           ↓
                              access_token (JWT) + refresh_token
                                           ↓
[Client] → GET /v1/cuoc-hop
  Headers: Authorization: Bearer <access_token>
           ↓
[auth_middleware.py]
  → decode JWT với SUPABASE_JWT_SECRET (python-jose)
  → verify: exp, iss, aud
  → inject user_id vào request.state.user_id
           ↓
[endpoint handler]
  → current_user = request.state.user_id
```

---

## 3. Các Pattern Quan Trọng

### Pattern 1: FastAPI Endpoint với Auth

```python
# api/v1/meeting_crud.py (ví dụ)
from fastapi import APIRouter, Depends, HTTPException, status, Request
from middleware.auth_middleware import require_auth
from services.meeting_crud_service import meeting_crud_service
from models.meeting import MeetingCreate, MeetingResponse

router = APIRouter(prefix="/v1", tags=["cuoc-hop"])

@router.post(
    "/cuoc-hop",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo cuộc họp mới",
)
async def create_meeting(
    body: MeetingCreate,
    request: Request,
    _: None = Depends(require_auth),  # inject auth check
) -> MeetingResponse:
    """Tạo một cuộc họp mới. Yêu cầu đăng nhập."""
    user_id: str = request.state.user_id
    try:
        meeting = await meeting_crud_service.create(user_id=user_id, data=body)
        return meeting
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
```

### Pattern 2: Auth Middleware (python-jose)

```python
# middleware/auth_middleware.py
from jose import JWTError, jwt
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.config import settings

security = HTTPBearer()

async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> None:
    """
    Verify Supabase JWT token.
    Inject user_id vào request.state.user_id.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase không set aud standard
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không hợp lệ: thiếu subject",
            )
        request.state.user_id = user_id
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token không hợp lệ hoặc đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

### Pattern 3: Supabase Client (async)

```python
# integrations/supabase_client.py
from supabase import create_async_client, AsyncClient
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)
_client: AsyncClient | None = None

async def get_supabase() -> AsyncClient:
    """Lazy singleton Supabase client."""
    global _client
    if _client is None:
        _client = await create_async_client(
            settings.supabase_url,
            settings.supabase_service_role_key,  # service role cho backend
        )
    return _client
```

### Pattern 4: Pydantic Model cho DB

```python
# models/meeting.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from uuid import UUID

class MeetingCreate(BaseModel):
    """Input để tạo cuộc họp mới."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    scheduled_at: datetime
    location: Optional[str] = Field(default=None, max_length=500)
    rule: str = Field(..., min_length=1, max_length=2000,
                      description="Điều kiện cuộc họp (sẽ gửi cho AI đánh giá)")

class MeetingResponse(BaseModel):
    """Response trả về sau khi tạo/lấy cuộc họp."""
    id: UUID
    owner_id: UUID
    title: str
    description: Optional[str]
    scheduled_at: datetime
    location: Optional[str]
    rule: str
    status: str  # pending | evaluated | ready | rescheduled
    created_at: datetime
    updated_at: datetime
```

### Pattern 5: Next.js API Call với Auth

```typescript
// lib/api.ts
import { createClient } from "@/lib/supabase/client";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiCall<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const supabase = createClient();
  const { data: { session } } = await supabase.auth.getSession();

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(session?.access_token
        ? { Authorization: `Bearer ${session.access_token}` }
        : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error?.error?.message ?? "Đã xảy ra lỗi không xác định");
  }

  return response.json() as Promise<T>;
}
```

### Pattern 6: React Query Hook

```typescript
// hooks/useCuocHop.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiCall } from "@/lib/api";
import { toast } from "sonner";
import type { Meeting, MeetingCreate } from "@/types/cuoc-hop";

export function useDanhSachCuocHop() {
  return useQuery({
    queryKey: ["cuoc-hop"],
    queryFn: () => apiCall<Meeting[]>("/v1/cuoc-hop"),
  });
}

export function useTaoCuocHop() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: MeetingCreate) =>
      apiCall<Meeting>("/v1/cuoc-hop", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cuoc-hop"] });
      toast.success("Đã tạo cuộc họp thành công!");
    },
    onError: (err: Error) => {
      toast.error(`Không thể tạo cuộc họp: ${err.message}`);
    },
  });
}
```

---

## 4. Edge Cases Cần Xử Lý

### Backend

| Case | Xử lý |
|------|-------|
| Token expired | 401 + `{"detail": "Token đã hết hạn"}` |
| Token invalid signature | 401 + `{"detail": "Token không hợp lệ"}` |
| User không có quyền xem meeting của người khác | 403 Forbidden |
| Meeting không tồn tại | 404 Not Found |
| CORS preflight (OPTIONS) | Handled by CORSMiddleware trong main.py |
| Rate limit exceeded | 429 Too Many Requests (đã có trong meetings.py) |
| LLM timeout | Fallback to deterministic parser (đã có) |
| Z3 timeout | Trả lỗi TIMEOUT với trace_id |
| Supabase connection fail | 503 Service Unavailable |

### Frontend

| Case | Xử lý |
|------|-------|
| Session expired | Redirect về `/dang-nhap` |
| API unreachable | Toast error + retry button |
| Form validation fail | React Hook Form + Zod error messages |
| AI evaluation timeout | Loading spinner + "Đang đánh giá..." message |
| Empty state (no meetings) | Illustration + CTA "Tạo cuộc họp đầu tiên" |

---

## 5. Environment Variables

### Backend (.env)

```bash
# App
APP_ENV=development
LOG_LEVEL=INFO

# Zero-setup master switches
USE_LLM=false
USE_FIREBASE=false
USE_GOOGLE_SERVICES=false

# Google Gemini (chỉ khi USE_LLM=true)
GEMINI_API_KEY=

# Firebase (chỉ khi USE_FIREBASE=true)
FIREBASE_PROJECT_ID=

# Supabase (mới — cho auth + CRUD)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_JWT_SECRET=your-jwt-secret

# Resend (mới — cho email)
RESEND_API_KEY=re_...

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://meetwise.vercel.app
```

### Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

---

## 6. Testing Strategy

### Backend Tests

```bash
# Chạy tất cả tests
python -m pytest tests/ -v

# Chạy từng nhóm
python -m pytest tests/test_api.py -v          # API integration tests (13+)
python -m pytest tests/test_solver.py -v       # Z3 engine tests
python -m pytest tests/test_fallback_parser.py -v  # Vietnamese parser
python -m pytest tests/test_actions.py -v      # Action service
```

**Test patterns hiện tại** (`tests/test_api.py`):
- `test_evaluate_ready_*`: Kiểm tra rule thỏa mãn → READY
- `test_evaluate_rescheduled_*`: Kiểm tra điều kiện chặn → RESCHEDULED
- `test_rate_limit_*`: Kiểm tra rate limiter
- `test_idempotency_*`: Kiểm tra cache idempotency
- `test_validation_*`: Kiểm tra Pydantic validation

### Frontend Tests (sẽ thêm)

```bash
cd frontend
npm run test           # Jest + React Testing Library
npm run test:e2e       # Playwright
```

---

## 7. Git Branch Strategy

```
main (protected — production)
  └── develop (integration)
        ├── feature/01-project-docs    ← ĐANG Ở ĐÂY
        ├── feature/02-backend-models
        ├── feature/03-backend-auth
        ├── feature/04-backend-meeting-crud
        ├── feature/05-backend-dashboard
        ├── feature/06-backend-notifications
        ├── feature/07-backend-email
        ├── feature/08-frontend-setup
        ├── feature/09-frontend-landing
        ├── feature/10-frontend-auth
        ├── feature/11-frontend-dashboard
        ├── feature/12-frontend-meetings
        ├── feature/13-frontend-evaluation
        ├── feature/14-tests
        ├── feature/15-docker-update
        └── feature/16-ci-cd
```

### Commit Convention

```
feat(scope): mô tả ngắn
fix(scope): mô tả lỗi đã sửa
test(scope): thêm/sửa tests
docs(scope): cập nhật tài liệu
chore(scope): cập nhật config/deps

Ví dụ:
feat(auth): implement JWT middleware với python-jose
feat(models): thêm Meeting model cho Supabase
test(auth): thêm unit tests cho auth_service
```

---

## 8. Checklist Triển Khai Mỗi Feature

Khi Claude tạo một feature mới, hãy kiểm tra:

- [ ] **Full file output** — không cắt xén code
- [ ] **Async/await** — tất cả I/O operations đều async
- [ ] **Error handling** — try/except với HTTPException cụ thể
- [ ] **Auth check** — protected endpoints đều có `Depends(require_auth)`
- [ ] **Input validation** — Pydantic model với validators
- [ ] **Tiếng Việt UI** — error messages, labels, descriptions
- [ ] **Logging** — logger.info/warning/error tại các điểm quan trọng
- [ ] **Tests** — ít nhất happy path + error path
- [ ] **Không đụng core** — agent/, solver/, schemas/ không bị thay đổi

---

## 9. Thứ Tự Khởi Tạo Services (Dependencies)

```
1. core/config.py              ← Settings (không dep)
2. core/logging.py             ← Logger (không dep)
3. integrations/supabase_client.py  ← Supabase (cần config)
4. middleware/auth_middleware.py     ← Auth (cần supabase + config)
5. services/auth_service.py         ← Auth service (cần supabase)
6. services/user_service.py         ← User service (cần supabase)
7. models/*.py                      ← Pydantic models (không dep)
8. services/meeting_crud_service.py ← Meeting service (cần supabase)
9. api/v1/auth.py                   ← Auth router (cần auth_service)
10. api/v1/users.py                 ← Users router (cần user_service + auth)
11. api/v1/meeting_crud.py          ← Meetings router (cần meeting_service + auth)
```

---

## 10. Known Issues & Gotchas

### Backend

1. **`_compiled_graph` singleton** (`agent/graph.py`): LangGraph compile chỉ một lần. Nếu test reset global state, cần reset `_compiled_graph = None`.

2. **`settings` là singleton** (`core/config.py`): `@lru_cache` — trong tests cần `get_settings.cache_clear()` nếu muốn override env vars.

3. **`asyncio.sleep` trong cleanup** (`main.py`): Background task chạy vô hạn. Khi shutdown, phải `cancel()` và `await` task.

4. **Supabase JWT decode**: Supabase không set `aud` claim standard. Phải dùng `options={"verify_aud": False}` trong python-jose.

5. **CORS cho localhost**: `cors_allowed_origins` mặc định là `"*"` cho dev. Production phải set explicit domains.

### Frontend

1. **Next.js App Router** dùng Server/Client Components phân biệt rõ. Dùng `"use client"` directive khi cần state hoặc browser APIs.

2. **Supabase client-side vs server-side**: Cần tạo 2 Supabase clients riêng (`lib/supabase/client.ts` và `lib/supabase/server.ts`).

3. **Hydration mismatch**: Tránh render thời gian (`new Date()`) trực tiếp trong Server Components.

---

*Tài liệu này được thiết kế để tối ưu context window của Claude. Đọc phần liên quan trước khi implement từng feature.*
