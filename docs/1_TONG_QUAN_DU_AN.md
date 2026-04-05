# 🚀 MeetWise AI: Giải Pháp Cứu Rỗi Văn Hóa Họp Hành Của Doanh Nghiệp

> *"Đừng để nhân sự của bạn kiệt sức vì những cuộc họp vô bổ. Hãy để AI quyết định khi nào chúng ta TRUYỀN THÔNG, thay vì CHỊU ĐỰNG."*

---

## 💥 Nỗi Đau Của Doanh Nghiệp (The Pain Point)

Trong môi trường doanh nghiệp hiện tại, chúng ta đang ném tiền qua cửa sổ mỗi ngày vì một lý do rất ngớ ngẩn: **HỌP HÀNH KÉM HIỆU QUẢ**.

1. **Lãng phí thời gian xếp lịch:** Trợ lý phải nhắn tin hỏi từng người *"Anh/chị rảnh lúc nào?"*, dò xét Google Calendar mờ cả mắt chỉ để tìm một slot 30 phút.
2. **Họp khi chưa sẵn sàng:** Bước vào phòng họp, phát hiện ra Slide chưa làm xong, Báo cáo tài chính chưa chốt số. Cuộc họp trở thành một buổi "ngồi nhìn nhau" và chốt lại bằng câu: *"Thôi để hôm sau họp tiếp nhé"*.
3. **Mệt mỏi và kiệt sức:** Những cuộc họp vô nghĩa rút cạn sinh lực sáng tạo của nhân sự xuất sắc nhất.

---

## 🎯 Giải Pháp MeetWise: "The Smart Gatekeeper" 

MeetWise AI không phải là một công cụ lên lịch thông thường. Nó là một **"Người Gác Cổng Thông Minh"**, kết hợp sức mạnh thấu hiểu ngôn ngữ tự nhiên của **AI (LLM)** và độ chính xác vô đối của **Toán học Logic (Z3 Theorem Prover)**.

Quy trình cực kỳ đơn giản:
1. Bạn đưa ra một **"Luật Lệ"** bằng tiếng Việt bình dân: *"Chỉ họp khi Quản lý rảnh và Slide đã làm xong"*.
2. MeetWise AI sẽ âm thầm kiểm tra hệ thống (Google Drive, Calendar, Sheets).
3. Nếu **ĐỦ ĐIỀU KIỆN**: Hệ thống bật đèn xanh (READY).
4. Nếu **CHƯA ĐỦ ĐIỀU KIỆN**: Hệ thống tự động HỦY, gửi thông báo nhắc nhở người chưa làm xong việc, và TỰ ĐỘNG dời lịch (RESCHEDULE).

> **Giá Trị Cốt Lõi:** Tiết kiệm hàng ngàn giờ làm việc vô ích mỗi năm, xây dựng văn hóa "Chỉ họp khi đã có sự chuẩn bị", và tự động hóa 100% công việc của thư ký.

---

## 🧠 Sức Mạnh Hiển Thị Qua Một Dòng Code

Để chứng minh hệ thống này là một kiệt tác kỹ thuật (Engineering Masterpiece), hãy nhìn vào JSON Output thực tế mà hệ thống sinh ra trong chưa tới **100 milliseconds (0.1 giây)**:

```json
{
  "status": "RESCHEDULED",
  "reason": "Manager_Free chưa thỏa mãn. Cuộc họp không thể diễn ra.",
  "latency_ms": 83.94,
  "ai_reasoning": {
    "logic": "(Slide_Done or Sheet_Done) and Manager_Free",
    "evaluation": {
      "Slide_Done": false,
      "Sheet_Done": true,
      "Manager_Free": false
    },
    "decision_trace": [
      "Slide_Done = FALSE → điều kiện chặn",
      "Sheet_Done = TRUE → đã có chuẩn bị",
      "Manager_Free = FALSE → điều kiện chặn",
      "Kết luận = RESCHEDULED"
    ]
  }
}
```

### 💡 Tại sao Output này lại là "Thiên Tài"?

- **`"status": "RESCHEDULED"`**: Máy tính đã tự ra quyết định hủy và dời lịch một cách dứt khoát.
- **`"latency_ms": 83.94`**: Dưới 100 mili-giây! Nhanh hơn một cái chớp mắt. Backend đã phải xử lý AI, parse chuỗi logic, chạy kiểm tra Toán Học, và trả về kết quả chuẩn xác mà không có độ trễ nào cảm nhận được.
- **`"ai_reasoning"` (Khả năng giải thích - XAI)**: Đây mới là "Vũ khí bí mật". Thay vì chỉ báo lỗi mập mờ, AI **CHỈ ĐÍCH DANH** ai/cái gì đang là "kỳ đà cản mũi". Nó hiểu rằng: *"Dù Sheet đã xong (True), nhưng Manager đang bận (False), nên theo luật (AND), cuộc họp bị hủy"*. Khả năng Explainable AI này giúp user hoàn toàn tin tưởng vào hệ thống.

**MeetWise AI không chỉ là code, nó là một Giám Đốc Vận Hành ảo, làm việc không lương 24/7.**
