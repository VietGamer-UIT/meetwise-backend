# 🏭 Giải Mã Hệ Thống MeetWise AI: "Công Ty Vận Hành Tự Động"

> *Bạn cảm thấy công nghệ Backend quá phức tạp? Đừng lo. Hãy tưởng tượng MeetWise AI không phải là phần mềm, mà là một **Công Ty Khổng Lồ** hoạt động cực kỳ trơn tru. Dưới đây là các phòng ban và nhân sự chủ chốt của chúng ta.*

---

## 1. ⚡ FastAPI: "Cô Tiếp Tân Siêu Tốc"
Khi khách hàng (Frontend) gửi một yêu cầu tới công ty, người đầu tiên họ gặp là **FastAPI**. 
Cô tiếp tân này có một khả năng kỳ diệu: Cô ấy có thể nhận cùng lúc **hàng ngàn cuộc điện thoại** mà không bị nghẽn mạng. Cô lấy thông tin, kiểm tra form điền đã đúng chưa (bằng Pydantic), và ngay lập tức phân phát hồ sơ vào các phòng ban bên trong. Nhanh, nhẹ, và không bao giờ càu nhàu.

---

## 2. 🧠 Gemini API (Parser): "Chuyên Gia Ngôn Ngữ"
Sếp (User) thường hay nói những câu rất chung chung: *"Chỉ họp khi ông Sếp rảnh và làm xong cái Slide"*.
Máy tính thì không hiểu tiếng người, nó chỉ hiểu `True/False` (Đúng/Sai). Vì vậy hồ sơ được đưa cho **Chuyên Gia Ngôn Ngữ Gemini**. Chuyên gia này sẽ "dịch" câu nói kia thành một phương trình toán học khô khan: 
`Logic: Slide_Done AND Manager_Free`

*(Lưu ý: Công ty rất thông minh. Nếu "Chuyên Gia" đang đi vắng hoặc bị đứt mạng, luôn có một **"Phiên Dịch Viên Dự Phòng" (Fallback Parser)** làm nhiệm vụ thay thế, đảm bảo công ty không bao giờ dừng hoạt động).*

---

## 3. ⚖️ Z3 Theorem Prover: "Bao Thanh Thiên Máu Lạnh"
Đây là "Vũ Khí Nguyên Tử" của chúng ta. Khi có công thức toán học từ bước 2, và tình hình thực tế thu thập được (VD: Mở lịch ra thấy Sếp không rảnh), hồ sơ được đưa ra tòa án của ngài **Z3 Theorem Prover**.

Z3 là một bộ giải toán học C++ xuất thân từ Microsoft Research. Đặc điểm của Z3 là:
- **Cực kỳ tốc độ & Chính xác 100%:** Z3 không phải là "AI đoán mò". Nó là Toán Học.
- **Máu lạnh, không cảm xúc:** Dù bạn có nài nỉ xin họp, nhưng Z3 tính ra `False` là `False`. Cả công ty sập cũng không làm thay đổi kết quả của Z3.
- Đây chính là chốt chặn cuối cùng ra phán quyết: **READY (Họp)** hay **RESCHEDULE (Dời lịch)**.

---

## 4. 🎼 LangGraph: "Vị Nhạc Trưởng Tài Ba"
Có Tiếp Tân, có Chuyên Gia, có Thẩm Phán. Vậy ai là người bảo họ phải làm việc theo thứ tự nào? Đó là **LangGraph (Nhạc trưởng)**. 

LangGraph vẽ ra một lộ trình công việc cực kỳ chặt chẽ (State Graph): 
`Dịch ngôn ngữ ➔ Thu thập Fact ➔ Đưa cho Bao Thanh Thiên xét xử ➔ Ra quyết định ➔ Gửi thông báo lấy tiền`. 
Nếu một bước hỏng, Nhạc trưởng sẽ linh hoạt chuyển sang phương án B (Smart Fallback). Nhờ có Nhạc trưởng, mọi thứ không bị rối tung lên.

---

## 5. 🔒 Idempotency Lock: "Bác Bảo Vệ Chống Kẹt Cửa"
Hãy tưởng tượng công ty có một cánh cửa quay. Khách hàng vì sốt ruột nên bấm nút `[Đánh giá cuộc họp]` 10 lần liên tục. Nếu cả 10 yêu cầu cùng tràn vào, công ty sẽ làm việc gấp 10 lần cho CÙNG MỘT SỰ VIỆC → Quá tải, tốn tiền API, tốn tài nguyên server.

May thay, chúng ta có **Idempotency Lock**. Khi khách bấm lần 1, bác bảo vệ lập tức **khóa cửa lại (Acquire Lock)**, treo biển *"ĐANG XỬ LÝ"*. 9 cú click chuột sau đó của khách sẽ bị bác bảo vệ chặn lại: *"Anh bình tĩnh, hồ sơ đang làm rồi, đừng nộp nữa"*. Khi làm xong, bác mở cửa trả kết quả cuối cùng cho tất cả một lượt. Không dư thừa, không thất thoát!
