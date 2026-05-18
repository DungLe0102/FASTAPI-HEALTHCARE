# Tài Liệu Kiểm Thử (Testing Documentation)

Tài liệu này bao gồm hướng dẫn kiểm thử thủ công qua Swagger UI và hướng dẫn chạy kiểm thử tự động (Unit Tests).

Tài liệu này là cẩm nang cầm tay chỉ việc, hướng dẫn bạn cách sử dụng giao diện Swagger (`http://localhost:8000/docs`) để test từng chức năng của hệ thống. 
Hệ thống đã được thiết kế tinh gọn với 2 vai trò duy nhất: **ADMIN** (Quản trị toàn quyền) và **PATIENT** (Bệnh nhân người dùng cuối).
 Run Command: `python -m uvicorn app.main:app --reload`

## Quy ước các Mã Trạng Thái (Status Code)
- **200 OK / 201 Created**: Thành công! (201 thường là khi tạo mới một dữ liệu).
- **400 Bad Request**: Bạn nhập sai thông tin (ví dụ: thiếu chữ, sai định dạng).
- **401 Unauthorized**: Lỗi xác thực. Bạn chưa đăng nhập (chưa gắn thẻ Auth).
- **403 Forbidden**: Lỗi quyền hạn. Bệnh nhân cố tình truy cập vào các API chỉ dành cho Admin.
- **404 Not Found**: Không tìm thấy dữ liệu (ví dụ: id bác sĩ không tồn tại).
- **409 Conflict**: Trùng lặp dữ liệu (ví dụ: email đã được đăng ký).

---

## BƯỚC 0: ĐĂNG NHẬP VÀ GẮN CHÌA KHÓA (AUTHORIZE)

1. Kéo lên đầu trang Swagger, tìm nút **`Authorize`** (màu xanh lá) hoặc biểu tượng ổ khóa 🔒 ở góc phải của API `/api/v1/auth/login`.
2. Điền thông tin đăng nhập:
   - **username**: Điền Email (Ví dụ tài khoản Admin: `admin@healthcare.local`).
   - **password**: Nhập mật khẩu (Ví dụ: `changethis`).
3. Bấm **Authorize**, sau đó bấm **Close**. Kể từ lúc này, hệ thống tự động ghi nhớ bạn là ai trong các lượt gọi API tiếp theo.

*(Lưu ý: Nếu bị báo lỗi 401 ở các API bên dưới, hãy làm lại Bước 0 này).*

---

## 1. MODULE TÀI KHOẢN VÀ XÁC THỰC (AUTH)

### 1.1. Bệnh nhân tự đăng ký tài khoản (`POST /api/v1/auth/signup`)
- **Cách làm**: Mở API, bấm **Try it out**.
- **Input**:
```json
{
  "email": "nguyenvana@gmail.com",
  "password": "Password123!"
}
```
- **Output Thành Công (201)**: Tạo tài khoản thành công. Trạng thái mặc định là PATIENT.

### 1.2. Khởi tạo Hồ sơ Bệnh nhân (`POST /api/v1/patients/me/profile`)
*Lưu ý: Bệnh nhân phải làm bước này ngay sau khi đăng ký để có thể đặt lịch.*
- **Input**: Bấm **Try it out**, nhập thông tin cá nhân.
```json
{
  "first_name": "Van A",
  "last_name": "Nguyen",
  "dob": "1990-01-01",
  "gender": "MALE",
  "phone": "0912345678",
  "cccd": "012345678901",
  "address": "Hà Nội"
}
```
- **Output Thành Công (201)**: Hồ sơ được liên kết trực tiếp với tài khoản (`patient_id` trùng với `account_id`).

### 1.3. Đăng nhập (`POST /api/v1/auth/login`)
- **Input**: Điền email vào ô **username**, và mật khẩu vào ô **password**.
- **Output (200)**: Cấp cho bạn Token và thông báo rõ Role của bạn (`ADMIN` hoặc `PATIENT`).

### 1.3. Lấy thông tin cá nhân (`GET /api/v1/auth/me`)
- *Chỉ bấm Execute, không cần nhập input.*
- **Output (200)**: Trả về thông tin của tài khoản đang đăng nhập.

---

## 2. MODULE CHUYÊN KHOA VÀ PHÒNG KHÁM (ADMIN)

*Yêu cầu: Đang đăng nhập bằng tài khoản ADMIN.*

### 2.1. Thêm chuyên khoa mới (`POST /api/v1/departments`)
- **Input**:
```json
{
  "name": "Khoa Nhi",
  "description": "Chuyên chăm sóc sức khỏe trẻ em"
}
```
- **Output (201)**: Sinh ra `department_id`. *Hãy copy mã UUID này để dùng cho bước tạo bác sĩ.*

### 2.2. Thêm phòng khám (`POST /api/v1/rooms`)
- **Input**:
```json
{
  "department_id": "DÁN-MÃ-KHOA-VÀO-ĐÂY",
  "room_number": "P.101",
  "room_type": "CONSULTATION",
  "capacity": 1
}
```
- **Output (201)**: Sinh ra `room_id`. *Copy mã này để xếp lịch.*

### 2.3. Vô hiệu hóa Khoa/Phòng (Soft Delete) (`DELETE /api/v1/departments/{department_id}`)
*Cập nhật mới:* Test tính năng vô hiệu hóa (Soft-Delete) vừa được vá lỗi.
- **Input**: Nhập `department_id`.
- **Output (200)**: Thuộc tính `is_active` sẽ chuyển thành `False`. Hệ thống cũng sẽ chặn việc tạo thêm Phòng khám (`ROOM`) mới nằm trong khoa đã bị vô hiệu hóa này (Trả về 400 Bad Request).

---

## 3. MODULE BÁC SĨ VÀ LỊCH LÀM VIỆC (ADMIN)
*(Lưu ý: Bác sĩ không có tài khoản đăng nhập. Họ là dữ liệu do Admin quản lý toàn quyền).*

### 3.1. Thêm Hồ sơ Bác sĩ (`POST /api/v1/doctors`)
- **Input**: Lấy `department_id` dán vào.
```json
{
  "department_id": "DÁN-MÃ-KHOA-VÀO-ĐÂY",
  "first_name": "Le",
  "last_name": "Xuan Dung",
  "specialization": "Nhi Khoa",
  "hourly_consultation_fee": 300000
}
```
- **Output (201)**: Lưu lại `doctor_id`.
*Lưu ý (Cập nhật)*: Hệ thống vừa được bổ sung lớp khiên bảo vệ. Nếu bạn cố tình nhập sai `department_id`, API sẽ trả về `404 Not Found` (Khoa không tồn tại) thay vì quăng lỗi DB `500 Internal Server Error` như trước đây!

### 3.2. Cài đặt lịch làm việc cho bác sĩ (`POST /api/v1/schedules`)
- **Input**: 
```json
{
  "doctor_id": "DÁN-MÃ-BÁC-SĨ",
  "room_id": "DÁN-MÃ-PHÒNG-KHÁM",
  "start_time": "2026-06-01T08:00:00Z",
  "end_time": "2026-06-01T12:00:00Z",
  "max_patients": 10
}
```
- **Output (201)**: Nhận `schedule_id`. Đây là khung giờ trống để bệnh nhân đặt.

---

## 4. MODULE BỆNH NHÂN VÀ BHYT

### 4.1. Xem hồ sơ cá nhân (`GET /api/v1/patients/me/profile`)
*Dành cho bệnh nhân.*
- **Output (200)**: Trả về thông tin hồ sơ đã tạo ở Bước 1.2. Các thông tin nhạy cảm như SĐT và CCCD sẽ được che bớt (masking) để bảo mật.

### 4.2. Quản lý Bệnh nhân (ADMIN Only) (`GET /api/v1/patients`)
- Admin có thể liệt kê và tìm kiếm bệnh nhân theo tên hoặc số điện thoại.

### 4.3. Thêm thẻ BHYT (`POST /api/v1/bhyt`)
- **Input**: Bệnh nhân dùng `patient_id` của mình (lấy từ `/api/v1/auth/me`).
```json
{
  "patient_id": "MÃ-BỆNH-NHÂN",
  "bhyt_code": "DN1234567890",
  "registered_hospital_code": "01001",
  "valid_from": "2026-01-01",
  "valid_to": "2026-12-31"
}
```

### 4.4. Xác minh thẻ BHYT (`PATCH /api/v1/bhyt/{bhyt_id}/verify`)
*CHỈ ADMIN mới làm được.*
- **Input**: Điền ID BHYT. Body nhập `{"check_status": "VERIFIED"}`.

---

## 5. MODULE ĐẶT LỊCH KHÁM (APPOINTMENT)

### 5.1. Đặt lịch khám (`POST /api/v1/appointments`)
*Bệnh nhân tự đặt lịch.*
- **Input**: Cần `patient_id` và `schedule_id`.
```json
{
  "patient_id": "MÃ-BỆNH-NHÂN",
  "schedule_id": "MÃ-LỊCH-BÁC-SĨ",
  "symptoms": "Đau bụng"
}
```
- **Output (201)**: Hệ thống sinh ra 1 Cuộc hẹn, đồng thời TỰ ĐỘNG TẠO hóa đơn (Billing). Trạng thái cuộc hẹn là `PENDING_PAYMENT`. 
  *Lưu ý: Bạn có 10 phút để thanh toán trước khi slot khám bị hủy tự động.*

---

## 6. MODULE THANH TOÁN VÀ LUỒNG KHÁM BỆNH

### 6.1. Bệnh nhân lấy mã VietQR (`POST /api/v1/billing/{billing_id}/vietqr`)
- **Input**: Dán `billing_id` vào tham số trên URL.
- **Output (200)**: Trả về Data URL hình ảnh mã QR Code ngân hàng.

### 6.2. Webhook Ngân Hàng - Thanh toán thành công (`POST /api/v1/billing/vietqr-webhook`)
*Giả lập ngân hàng gọi về hệ thống.*
- **Input**:
```json
{
  "error": 0,
  "message": "Giao dịch thành công",
  "data": [
    {
      "amount": 300000,
      "description": "PAY MÃ-GIAO-DỊCH",
      "reference_number": "FT123456789"
    }
  ]
}
```
- **Output (200)**: Cuộc hẹn chuyển sang `SCHEDULED` (Đã chốt lịch).

### 6.3. Admin Ghi nhận Bệnh Án (`POST /api/v1/medical-records`)
*Admin thao tác thay cho bác sĩ sau khi khám xong.*
- **Input**:
```json
{
  "patient_id": "MÃ-BỆNH-NHÂN",
  "appointment_id": "MÃ-CUỘC-HẸN",
  "doctor_id": "MÃ-BÁC-SĨ",
  "diagnosis": "Viêm dạ dày cấp",
  "treatment_plan": "Uống thuốc, kiêng đồ chua cay"
}
```

### 6.4. Admin Đóng Cuộc Hẹn (`PATCH /api/v1/appointments/{appointment_id}/status`)
- **Input**: Đổi trạng thái sang `COMPLETED` (Hoàn thành).

### 6.5. Admin Hoàn tiền qua VietQR (`POST /api/v1/payments/vietqr-refund`)
*Chỉ ADMIN mới làm được. Dùng khi khách hàng hủy lịch sau khi đã thanh toán thành công qua VietQR.*
- **Input**: Lấy `transaction_id` (trạng thái SUCCESS) từ hóa đơn.
```json
{
  "transaction_id": "MÃ-GIAO-DỊCH",
  "amount": 300000,
  "content": "Hoan tien do huy kham"
}
```
- **Output (200)**: API tự động gọi sang hệ thống VietQR để thực hiện hoàn tiền. Trạng thái giao dịch sẽ đổi thành `REFUNDED` và hóa đơn sẽ cập nhật lại (về `UNPAID` hoặc `PARTIAL`).

## 7. MODULE TÀI CHÍNH VÀ THANH TOÁN BÁC SĨ (ADMIN)

### 7.1. Tính toán thu nhập dự kiến cho bác sĩ (`POST /api/v1/doctor-payouts/calculate-earnings`)
- **Cách làm**: Admin kiểm tra xem bác sĩ đã làm được bao nhiêu tiền trong một khoảng thời gian (dựa trên các ca `COMPLETED`).
- **Input**:
```json
{
  "doctor_id": "MÃ-BÁC-SĨ",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30"
}
```
- **Output (200)**: Trả về tổng số ca đã khám và tổng tiền tương ứng.

### 7.2. Lập lịch thanh toán cho bác sĩ (`POST /api/v1/doctor-payouts/`)
- **Cách làm**: Admin tạo lệnh thanh toán để kế toán thực hiện chuyển tiền.
- **Input**:
```json
{
  "doctor_id": "MÃ-BÁC-SĨ",
  "amount": 5000000,
  "payout_date": "2026-07-05",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "notes": "Thanh toán lương tháng 6"
}
```
- **Output (201)**: Tạo bản ghi thanh toán ở trạng thái `PENDING`.

### 7.3. Xem danh sách các khoản thanh toán (`GET /api/v1/doctor-payouts/`)
- **Cách làm**: Có thể lọc theo `doctor_id` hoặc `status` (PENDING/PAID).

### 7.4. Chốt thanh toán (Đã trả tiền) (`PATCH /api/v1/doctor-payouts/{payout_id}`)
- **Input**: Gửi body `{"status": "PAID"}` để xác nhận tiền đã được chuyển cho bác sĩ.

---

## 💡 MẸO SỬA LỖI NHANH (TROUBLESHOOTING)
1. **Lỗi 401**: Bạn chưa đăng nhập. Lập tức kéo lên trên cùng, bấm nút `Authorize` xanh lá, điền email và password.
2. **Lỗi 403**: Bệnh nhân (PATIENT) đang cố tình truy cập vào các API quản lý nội bộ. Hãy đăng nhập bằng email `admin@healthcare.local` / `changethis` để được cấp toàn quyền.
3. **Lỗi 400**: Thường do bạn copy dư khoảng trắng hoặc nhập sai định dạng JSON. Bấm xem ô chữ đỏ "Response body" ở bên dưới để đọc chi tiết lỗi.
4. **Lỗi 404**: Cóp nhầm ID (UUID) từ bước trước. Hãy chắc chắn copy đúng đoạn mã (ví dụ: `c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39`).

---

## 8. MODULE ĐƠN HÀNG VÀ GIA HẠN (ORDER)

### 8.1. Đặt lệnh gia hạn BHYT (`POST /api/v1/orders/`)
*Bệnh nhân tự tạo yêu cầu gia hạn thẻ BHYT.*
- **Input**: Cần `patient_id` và `bhyt_id`. Số tháng từ 6-12.
```json
{
  "patient_id": "MÃ-BỆNH-NHÂN",
  "order_type": "BHYT_EXTENSION",
  "bhyt_id": "MÃ-BHYT",
  "extension_months": 6
}
```
- **Output (201)**: Trả về đơn hàng có trạng thái `PENDING`, tự động tính toán tổng tiền (`total_amount`) và tạo link `qr_url` để thanh toán. 

### 8.2. Đặt lệnh mua thuốc (`POST /api/v1/orders/`)
*Bệnh nhân đặt thuốc trực tuyến.*
- **Input**: Truyền danh sách ID các loại thuốc.
```json
{
  "patient_id": "MÃ-BỆNH-NHÂN",
  "order_type": "PHARMACY",
  "items": [
    {
      "item_id": "MÃ-THUỐC",
      "quantity": 2
    }
  ]
}
```
- **Output (201)**: Tương tự như gia hạn BHYT, sinh ra mã QR. Hủy tự động sau 10 phút nếu không thanh toán.

---

## 9. KIỂM THỬ TỰ ĐỘNG (AUTOMATED UNIT TESTS)

Ngoài việc test thủ công trên Swagger, hệ thống đã được trang bị bộ Unit Test để đảm bảo tính ổn định của logic nghiệp vụ.

### 9.1. Cách chạy test
Mở terminal tại thư mục gốc của dự án và chạy lệnh sau:
```powershell
python -m unittest discover tests
```

### 9.2. Cấu trúc bộ test
- **`tests/test_security.py`**: Kiểm tra logic mã hóa mật khẩu và tạo Token JWT.
- **`tests/test_services/`**: Kiểm tra logic nghiệp vụ (Services):
    - `test_department.py`: Logic Khoa/Phòng và khởi tạo chuẩn.
    - `test_doctor.py`: Logic quản lý Bác sĩ và Lịch khám.
    - `test_patient.py`: Logic Bệnh nhân và thẻ BHYT.
    - `test_appointment.py`: Quy trình đặt lịch và State Machine.
    - `test_medical_record.py`: Hồ sơ bệnh án và ký số SHA-256.
    - `test_billing.py`: Hóa đơn, thanh toán và Webhook VietQR.
    - `test_inventory_order.py`: Quản lý kho thuốc (FIFO) và đơn hàng Pharmacy/BHYT.
    - `test_notification.py`: Hệ thống thông báo và hỗ trợ (Support Request).
- **`tests/test_api/`**: Kiểm tra các đầu API thực tế (Integration Tests):
    - `test_department_api.py`: Tương tác API Khoa/Phòng.

### 9.3. Lưu ý kỹ thuật
- Toàn bộ test sử dụng **SQLite in-memory**, vì vậy nó sẽ **không ảnh hưởng** đến dữ liệu thật trong database Postgres của bạn.
- Mỗi khi chạy test, một database ảo mới sẽ được tạo ra và xóa đi ngay sau khi hoàn thành.
