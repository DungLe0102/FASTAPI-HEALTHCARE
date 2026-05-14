<div align="center">
  <img src="https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png" alt="FastAPI" width="400"/>
  <h1>🏥 HEALTHCARE MANAGEMENT SYSTEM</h1>
  <p><i>A robust, modular, and high-performance backend solution for modern healthcare clinics & hospitals.</i></p>

  [![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
  [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
  [![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![VietQR](https://img.shields.io/badge/Payment-VietQR-blue?style=for-the-badge)](#)
</div>

---

## 📖 Giới thiệu (Overview)

Hệ thống quản lý Y tế toàn diện được xây dựng bằng **FastAPI** và **PostgreSQL**. Kiến trúc được thiết kế theo mô hình **Modular Monolith** kết hợp với **Role-Based Access Control (RBAC)** nghiêm ngặt, đảm bảo tính mở rộng cao, bảo mật tuyệt đối và hiệu năng vượt trội.

Hệ thống cung cấp trọn bộ giải pháp từ:
- Quản lý Hồ sơ Bệnh nhân & Khám chữa bệnh.
- Đặt lịch trực tuyến (Appointment Booking).
- Quản lý Dược phẩm & Đơn thuốc (Pharmacy & Inventory).
- Quản lý Tài chính, Hoàn tiền tự động & Lương Bác sĩ qua **VietQR**.

---

## ✨ Tính năng nổi bật (Key Features)

### 👥 Phân quyền thông minh (RBAC)
- Tách biệt luồng nghiệp vụ giữa **ADMIN** (Quản lý toàn diện) và **PATIENT** (Người dùng cuối).
- Cơ chế bảo mật JWT Auth mạnh mẽ.

### 📅 Đặt lịch khám thông minh (Smart Appointment)
- Bệnh nhân tự động đặt lịch theo khung giờ trống của Bác sĩ.
- Giữ slot tự động (Locked until payment) trong 10 phút. Tự động giải phóng nếu không thanh toán.

### 💳 Tích hợp Thanh toán tự động (VietQR Automation)
- Sinh mã QR động cho từng hóa đơn.
- Webhook tự động nhận thông báo biến động số dư và chốt lịch ngay lập tức.
- **Tính năng đặc biệt**: Hỗ trợ API Refund một chạm để hoàn tiền cho bệnh nhân khi hủy lịch.

### 💊 Quản lý Lâm sàng & Kho Dược
- Lưu trữ hồ sơ bệnh án, kê đơn thuốc và chỉ định dịch vụ cận lâm sàng.
- Quản lý tồn kho theo Batch, trừ kho tự động khi xuất thuốc.

---

## 🛠️ Công nghệ sử dụng (Tech Stack)

| Thành phần | Công nghệ |
|------------|----------|
| **Core Framework** | FastAPI (Python 3.10+) |
| **Database** | PostgreSQL |
| **ORM** | SQLAlchemy 2.0 |
| **Migration** | Alembic |
| **Authentication** | JWT (JSON Web Tokens) |
| **3rd Party Integration** | VietQR API, SMTP Email |

---

## 🚀 Hướng dẫn Cài đặt (Installation & Setup)

### 1. Clone repository
```bash
git clone https://github.com/DungLe0102/FASTAPI-HEALTHCARE.git
cd FASTAPI-HEALTHCARE
```

### 2. Thiết lập môi trường ảo (Virtual Environment)
```bash
python -m venv venv
source venv/bin/activate  # Trên Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Cấu hình biến môi trường
Sao chép file cấu hình mẫu và điền thông tin của bạn:
```bash
cp .env.example .env
```
*Lưu ý: Bạn cần cấu hình `DATABASE_URL` để kết nối tới PostgreSQL, và `VIETQR_SECRET_KEY` nếu muốn dùng tính năng thanh toán.*

### 4. Khởi tạo Database (Migrations)
```bash
alembic upgrade head
```

### 5. Khởi động Server
```bash
fastapi dev app/main.py
```
> 🎉 **Swagger UI:** `http://localhost:8000/docs`

---

## 📂 Cấu trúc thư mục (Folder Structure)

Hệ thống tuân thủ kiến trúc phân tầng rõ ràng (N-Tier Architecture):

```text
├── alembic/              # File migration database
├── app/
│   ├── models/           # SQLAlchemy Entities (Database schemas)
│   ├── schemas/          # Pydantic Models (DTOs - Data Transfer Objects)
│   ├── routers/          # API Endpoints (Controllers)
│   ├── services/         # Business Logic xử lý cốt lõi
│   ├── db.py             # Database Connection Session
│   ├── config.py         # App Configuration Settings
│   └── main.py           # Application Entrypoint
├── test.md               # Cẩm nang Hướng dẫn Test API qua Swagger
└── database_erd.md       # Sơ đồ CSDL hệ thống (ERD Diagram)
```

---

## 📚 Tài liệu tham khảo
- Chi tiết API và hướng dẫn test: Vui lòng xem `test.md`.
- Sơ đồ quan hệ CSDL: Vui lòng xem `database_erd.md`.

<div align="center">
  <i>Được phát triển với ❤️ và sự tận tâm!</i>
</div>
