# 🔌 Thiết Kế Tích Hợp: Cẩm Nang Dành Cho Frontend Developer

> *"Chào người anh em Frontend (FE)! Backend của MeetWise đã được 'rèn' ở mức độ Production-Ready. Mọi thứ rất trơn tru, bạn chỉ cần gọi API đúng chuẩn và làm theo một vài best practice nhỏ dưới đây là ứng dụng của chúng ta sẽ rất WOW."*

---

## 🛠 1. Cấu Trúc Request API Tối Thượng

Endpoint duy nhất bạn cần quan tâm:
`POST /v1/meetings/evaluate`

### 1a. Payload Chuẩn (JSON Mode)
```json
{
  "meeting_id": "weekly-sync-w15",
  "rule": "Slide cập nhật hoặc Sheet chốt số, bắt buộc Manager rảnh",
  "override_facts": null
}
```

### 1b. Payload Giả Lập (Hackathon / Demo Mode)
Nếu bạn không muốn dính dáng tới các API thật của Google (Calendar, Drive) chạy chậm, hãy tận dụng "Tính năng ăn gian" siêu đỉnh của BE: truyền thẳng tham số `override_facts`!

```json
{
  "meeting_id": "demo-conflict-01",
  "rule": "(Slide_Done or Sheet_Done) and Manager_Free",
  "override_facts": {
    "Slide_Done": false,
    "Sheet_Done": true,
    "Manager_Free": false
  }
}
```
*Ghi chú: Khi nhét `override_facts` vào, Backend tự hiểu là đang diễn tập và trả kết quả cái vèo.*

---

## 🎨 2. Phân Tích Response Từ Backend

Backend không trả về lỗi 500 kèm stack trace làm crash App của bạn đâu. Khi thành công (HTTP 200), bạn sẽ nhận được Payload siêu mượt:

```json
{
  "trace_id": "uuid-request-id-1234",
  "meeting_id": "demo-conflict-01",
  "status": "RESCHEDULED", // Hoặc "READY"
  "reason": "Điều kiện chưa thỏa mãn. Cuộc họp không thể diễn ra.",
  "actions": [
    {
       "type": "NOTIFY",
       "target": "Manager",
       "status": "sent",
       ...
    }
  ],
  "ai_reasoning": {
    "logic": "(Slide_Done or Sheet_Done) and Manager_Free",
    "evaluation": { ... },
    "decision_trace": [...] // Hãy show cái mảng chữ này lên UI để khè User!
  }
}
```

---

## 💎 3. Lời Khuyên "Vàng" Cho Trải Nghiệm Frontend (UX)

### ⏳ A. Hiệu ứng Loading Spinner "Thông Minh"
- Backend này được trang bị **Idempotency Lock**. Nó có nghĩa là: Bất kể 1 user click đúp (Double-click) hoặc spam nút Submit bao nhiêu lần, BE sẽ khóa ngay từ request thứ 2 để chặn spam (trả mã `HTTP 409 Conflict`).
- **Nhiệm vụ của FE:** Vừa bấm Submit xong, hãy **disable ngay button đó**, bôi màu xám và phủ lên một con Spinner quay đều.
- Nếu lỡ dính `409 Conflict` (Meeting đang được xử lý), đừng pop-up ERROR đỏ lòm dọa User. Đơn giản là vẫn cứ hiện Spinner quay chờ một chút, hiển thị Toast: *"Đang có người khác cũng tính điểm cuộc họp này, vui lòng chờ..."*.

### ⚡ B. Đừng chặn UI (Non-blocking)
- Có thể thao tác "gọi LLM Gemini" thi thoảng bị chậm 1-2 giây. Hãy thêm một vài dòng chữ nhấp nháy bên dưới con Spinner để User không tưởng App bị đứng:
  - *`"Đang biên dịch ngôn ngữ..."`* (Giây 1)
  - *`"Bao Thanh Thiên Z3 đang xử án..."`* (Giây 2)
  - *`"Đang ra quyết định..."`* (Giây 3)

### 🛡 C. Handle Retry tự động
Nếu BE gặp nghẽn mạng LLM, đội BE đã cài chế độ **Fallback Parser (Tự biên dịch không cần AI, bao sống 100%)**. Do đó, FE không cần phải làm logic "Auto-Retry" một cách mù quáng nữa. Cứ quăng request cho BE, BE sẽ lo chuyện sống còn!
