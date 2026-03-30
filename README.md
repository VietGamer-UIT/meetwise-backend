# MeetWise Backend

> **Meeting Readiness Evaluation Engine** — Neuro-Symbolic AI Agent  
> Đánh giá sự sẵn sàng của cuộc họp bằng logic Z3 Solver + LLM (optional)

[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://docker.com)
[![Python](https://img.shields.io/badge/python-3.11-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

---

## ⚡ Chạy ngay — 1 lệnh

```bash
docker compose up --build
```

> **Không cần API key. Không cần config. Chạy được ngay.**

---

## 📋 Mục lục

- [Yêu cầu](#yêu-cầu)
- [Chạy local](#chạy-local)
- [API Docs](#api-docs)
- [Example request](#example-request-curl)
- [Response mẫu](#response-mẫu)
- [Cấu hình](#cấu-hình-nâng-cao)
- [Frontend integration](#frontend-integration)

---

## Yêu cầu

| Tool | Version |
|------|---------|
| Docker | ≥ 24.x |
| Docker Compose | ≥ 2.x |

> Không cần Python, pip, virtualenv — Docker lo hết.

---

## Run local

```bash
uvicorn main:app --reload
```

## Run Docker

```bash
docker compose up --build
```

## Deploy to Cloud Run

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT/meetwise

gcloud run deploy meetwise \
  --image gcr.io/YOUR_PROJECT/meetwise \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated
```

## API docs

http://localhost:8000/docs


---

## Example Request (curl)

### Đánh giá cuộc họp

```bash
curl -X POST http://localhost:8000/v1/meetings/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "meeting_id": "q1-kickoff-2024",
    "rule": "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh",
    "facts": {
      "Slide_Done": false,
      "Sheet_Done": true,
      "Manager_Free": false
    }
  }'
```

### Kiểm tra trạng thái cuộc họp

```bash
curl http://localhost:8000/v1/meetings/q1-kickoff-2024/status
```

### Health check

```bash
curl http://localhost:8000/health
```

---

## Response mẫu

### RESCHEDULED (có actions)

```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "meeting_id": "q1-kickoff-2024",
  "status": "RESCHEDULED",
  "reason": "Điều kiện bắt buộc 'Manager_Free' chưa thỏa mãn.",
  "unsatisfied_conditions": ["Manager_Free"],
  "actions": [
    {
      "type": "NOTIFY",
      "target": "Manager",
      "status": "sent",
      "message": "Cuộc họp không thể diễn ra..."
    },
    {
      "type": "RESCHEDULE",
      "target": null,
      "status": "sent",
      "proposed_time": "2026-04-01T10:00:00"
    }
  ],
  "latency_ms": 45.2
}
```

### READY

```json
{
  "trace_id": "abc123",
  "meeting_id": "q1-kickoff-2024",
  "status": "READY",
  "reason": "Tất cả điều kiện đã được thỏa mãn.",
  "unsatisfied_conditions": [],
  "actions": [],
  "latency_ms": 12.5
}
```

---

## Cấu hình nâng cao

Sửa file `.env` để bật các tính năng nâng cao:

### Bật Gemini LLM

```env
USE_LLM=true
GEMINI_API_KEY=your-api-key
GEMINI_MODEL=gemini-1.5-flash
```

### Bật Google Chat notification

```env
USE_GOOGLE_SERVICES=true
GOOGLE_CHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/...
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
```

### Bật Firebase Firestore

```env
USE_FIREBASE=true
FIREBASE_PROJECT_ID=your-project-id
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
```

### CORS cho Frontend

```env
# Development
CORS_ALLOWED_ORIGINS=*

# Production
CORS_ALLOWED_ORIGINS=https://app.meetwise.ai,http://localhost:3000
```

---

## Kiến trúc

```
POST /v1/meetings/evaluate
         │
    [Rate Limit] → [Sanitize] → [Idempotency]
         │
    LangGraph Pipeline:
    ┌─ parse_input  ─── Fallback Parser (deterministic) | Gemini LLM (optional)
    ├─ fetch_facts  ─── Mock Google APIs | Real APIs (optional)
    ├─ verify_logic ─── Z3 SMT Solver (luôn bật)
    └─ decide_action ── READY | RESCHEDULED
                              ↓ (nếu RESCHEDULED)
                        execute_actions() — asyncio.gather
                        ├── NOTIFY → [MOCK CHAT] log | Google Chat
                        └── RESCHEDULE → fixed time | Google Calendar
```

**Zero-Setup mode**: fallback parser + mock APIs + in-memory storage  
**Full mode**: Gemini LLM + Google Workspace APIs + Firebase Firestore

---

## Frontend Integration

> **Câu hỏi: Frontend có cần backend open-source không?**

**KHÔNG.** Frontend chỉ cần backend **chạy** (local hoặc deployed):

- Frontend gọi API qua URL: `http://localhost:8000` hoặc `https://api.meetwise.ai`
- Frontend đọc API contract từ Swagger: `http://localhost:8000/docs`
- Backend có thể là private repo, deployed server, Docker container — không quan trọng
- Chỉ cần CORS được cấu hình đúng: `CORS_ALLOWED_ORIGINS=http://localhost:3000`

```javascript
// Frontend example (React/Vue/etc.)
const response = await fetch('http://localhost:8000/v1/meetings/evaluate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    meeting_id: 'q1-2024',
    rule: 'Manager rảnh và Slide xong',
    facts: { Manager_Free: false, Slide_Done: true }
  })
});
const data = await response.json();
console.log(data.status); // "READY" hoặc "RESCHEDULED"
```

---

## Security

- `.env` bị `.gitignore` chặn — **không bao giờ commit secrets**
- `credentials.json` bị chặn
- Service Account JSON bị chặn
- Docker image không chứa `.env` (bị xóa trong build)

---

## Tests

```bash
pytest tests/ -v
pytest tests/test_fallback_parser.py -v   # test fallback parser
pytest tests/test_actions.py -v           # test action service
```

---

## Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/v1/meetings/evaluate` | Đánh giá + execute actions |
| `GET` | `/v1/meetings/{id}/status` | Lifecycle status |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Service metrics |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc UI |
