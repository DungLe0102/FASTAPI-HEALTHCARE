"""
Router: Thông báo & Yêu cầu hỗ trợ
=====================================
Prefix  : /api/v1
Tags    : 8. System - Notifications & Support

Luồng thông báo tự động:
  - Đặt lịch thành công → bệnh nhân nhận thông báo xác nhận
  - Thanh toán thành công → thông báo lịch hẹn được chốt
  - Ký đơn thuốc → thông báo thuốc sẵn sàng lấy
  - BHYT sắp hết hạn → cảnh báo (chạy qua CRON /notifications/cron/bhyt-expiry)

Luồng hỗ trợ khách hàng:
  1. POST /support-requests         — bệnh nhân gửi yêu cầu hỗ trợ
  2. GET  /support-requests         — Admin xem danh sách ticket
  3. PATCH /support-requests/{id}   — Admin cập nhật trạng thái và phản hồi
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.notification import (
    NotificationCreate, NotificationResponse,
    SupportRequestCreate, SupportRequestUpdate, SupportRequestResponse,
)
from app.services import notification_service as svc
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["8. System - Notifications & Support"])


# ─────────────────────────────────────────────────────────────
# THÔNG BÁO HỆ THỐNG (NOTIFICATION)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/notifications",
    response_model=List[NotificationResponse],
    summary="Xem danh sách thông báo",
)
def list_notifications(
    recipient_id : Optional[UUID] = Query(None, description="[ADMIN] Lọc theo người nhận. Bệnh nhân không cần truyền — tự động lấy của mình"),
    status_filter: Optional[str]  = Query(None, description="Lọc theo trạng thái: PENDING / SENT / FAILED"),
    skip         : int            = Query(0, ge=0, description="Bỏ qua N bản ghi"),
    limit        : int            = Query(50, ge=1, le=200, description="Số lượng tối đa"),
    db           : Session        = Depends(get_db),
    current_acc  : Account        = Depends(get_current_account),
):
    """
    **Xem danh sách thông báo của bản thân hoặc của bệnh nhân cụ thể (Admin).**

    **Với PATIENT:** Không cần truyền `recipient_id` — hệ thống tự động lọc theo tài khoản đang đăng nhập.

    **Với ADMIN:** Có thể truyền `recipient_id` để xem thông báo của bất kỳ người dùng nào.
    Nếu không truyền, xem tất cả thông báo trong hệ thống.

    **Lọc theo trạng thái:**
    - `PENDING`: chưa gửi
    - `SENT`: đã gửi email thành công
    - `FAILED`: gửi thất bại (cần kiểm tra SMTP)
    """
    if current_acc.role != "ADMIN":
        if recipient_id and recipient_id != current_acc.account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Từ chối: Bạn chỉ được xem thông báo của chính mình"
            )
        recipient_id = current_acc.account_id
    return svc.list_notifications(db, recipient_id, status_filter, skip, limit)


@router.post(
    "/notifications",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Tạo thông báo thủ công",
)
def create_notification(
    payload    : NotificationCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Gửi thông báo thủ công đến người dùng.

    Thường dùng cho các thông báo không thuộc luồng tự động:
    - Thông báo lịch nghỉ lễ phòng khám
    - Thông báo thay đổi chính sách
    - Nhắc nhở kết quả xét nghiệm

    Hệ thống sẽ gửi email qua SMTP nếu được cấu hình trong `.env`.

    - **recipient_id**: UUID người nhận
    - **recipient_type**: `PATIENT` / `ADMIN`
    - **notification_type**: `APPOINTMENT` / `PAYMENT` / `PRESCRIPTION` / `BHYT_EXPIRATION` / `SUPPORT` / `GENERAL`
    - **channel**: `EMAIL` / `SMS` / `IN_APP`
    - **title**: tiêu đề thông báo
    - **content**: nội dung chi tiết
    """
    return svc.create_notification(db, payload)


@router.patch(
    "/notifications/{notification_id}/sent",
    response_model=NotificationResponse,
    summary="[ADMIN/Worker] Đánh dấu thông báo đã gửi thành công",
)
def mark_sent(
    notification_id: UUID,
    db             : Session = Depends(get_db),
    current_acc    : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Hệ thống nội bộ]** Worker gửi email gọi endpoint này để xác nhận đã gửi thành công.

    Chuyển trạng thái thông báo từ `PENDING` → `SENT` và ghi nhận thời điểm gửi.
    """
    return svc.mark_sent(db, notification_id)


@router.patch(
    "/notifications/{notification_id}/failed",
    response_model=NotificationResponse,
    summary="[ADMIN/Worker] Đánh dấu thông báo gửi thất bại",
)
def mark_failed(
    notification_id: UUID,
    db             : Session = Depends(get_db),
    current_acc    : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Hệ thống nội bộ]** Worker gửi email gọi endpoint này khi gặp lỗi SMTP.

    Chuyển trạng thái từ `PENDING` → `FAILED`.
    Admin có thể xem danh sách `FAILED` để kiểm tra cấu hình SMTP.
    """
    return svc.mark_failed(db, notification_id)


@router.post(
    "/notifications/cron/bhyt-expiry",
    summary="[CRON] Tự động tạo cảnh báo thẻ BHYT sắp hết hạn",
)
def bhyt_expiry_alerts(
    days_before: int     = Query(30, ge=1, description="Cảnh báo trước bao nhiêu ngày (mặc định 30)"),
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Tác vụ hệ thống — gọi định kỳ bởi Cron Job]**

    Quét tất cả bệnh nhân có thẻ BHYT sẽ hết hạn trong N ngày tới,
    tạo thông báo cảnh báo cho những người **chưa được thông báo** trong 60 ngày qua.

    - **days_before=30** *(mặc định)*: cảnh báo khi còn 30 ngày hết hạn
    - **days_before=7**: cảnh báo khẩn cấp 1 tuần trước khi hết hạn

    **Khuyến nghị:** Chạy 1 lần/ngày vào 8 giờ sáng:
    ```
    0 8 * * * curl -X POST "http://localhost:8000/api/v1/notifications/cron/bhyt-expiry?days_before=30" \\
      -H "Authorization: Bearer <admin_token>"
    ```

    **Tránh spam:** Mỗi bệnh nhân chỉ nhận tối đa 1 cảnh báo trong 60 ngày.
    """
    count = svc.create_bhyt_expiry_alerts(db, days_before)
    return {"detail": f"Đã tạo {count} thông báo cảnh báo hết hạn BHYT"}


# ─────────────────────────────────────────────────────────────
# YÊU CẦU HỖ TRỢ (SUPPORT REQUEST / TICKET)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/support-requests",
    response_model=List[SupportRequestResponse],
    summary="[ADMIN] Danh sách yêu cầu hỗ trợ từ bệnh nhân",
)
def list_requests(
    status_filter: Optional[str] = Query(None, description="Lọc theo trạng thái: OPEN / IN_PROGRESS / RESOLVED / CLOSED"),
    priority     : Optional[str] = Query(None, description="Lọc theo mức độ ưu tiên: LOW / MEDIUM / HIGH / URGENT"),
    skip         : int           = Query(0, ge=0),
    limit        : int           = Query(50, ge=1, le=200),
    db           : Session       = Depends(get_db),
    current_acc  : Account       = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Xem danh sách tất cả yêu cầu hỗ trợ từ bệnh nhân.

    **Bộ lọc hữu ích:**
    - `status_filter=OPEN`: xem ticket mới chưa xử lý
    - `status_filter=IN_PROGRESS`: đang trong quá trình giải quyết
    - `priority=URGENT`: xem các vấn đề khẩn cấp trước

    **Ví dụ xem ticket URGENT chưa xử lý:**
    `GET /support-requests?status_filter=OPEN&priority=URGENT`
    """
    return svc.list_support_requests(db, status_filter, priority, skip, limit)


@router.post(
    "/support-requests",
    response_model=SupportRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gửi yêu cầu hỗ trợ / phản ánh vấn đề",
)
def create_request(
    payload    : SupportRequestCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Bệnh nhân gửi yêu cầu hỗ trợ hoặc phản ánh vấn đề.**

    Mọi người dùng có tài khoản đều có thể gửi yêu cầu hỗ trợ.

    - **subject**: tiêu đề ngắn gọn vấn đề (VD: "Không thể đặt lịch khám")
    - **content**: mô tả chi tiết vấn đề
    - **priority**: `LOW` / `MEDIUM` / `HIGH` / `URGENT` *(tùy chọn, mặc định MEDIUM)*
    - **category** *(tùy chọn)*: `APPOINTMENT` / `PAYMENT` / `TECHNICAL` / `OTHER`

    Sau khi gửi, Admin sẽ phản hồi qua hệ thống thông báo.
    Bạn có thể theo dõi trạng thái qua `GET /support-requests/{id}` nếu có.
    """
    return svc.create_support_request(db, payload)


@router.patch(
    "/support-requests/{request_id}",
    response_model=SupportRequestResponse,
    summary="[ADMIN] Cập nhật trạng thái và phản hồi yêu cầu hỗ trợ",
)
def update_request(
    request_id : UUID,
    payload    : SupportRequestUpdate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Xử lý và cập nhật yêu cầu hỗ trợ của bệnh nhân.

    - **status**: chuyển trạng thái — `IN_PROGRESS` / `RESOLVED` / `CLOSED`
    - **response_note** *(tùy chọn)*: nội dung phản hồi gửi cho bệnh nhân
    - **priority** *(tùy chọn)*: điều chỉnh mức ưu tiên nếu cần

    **Quy trình xử lý ticket:**
    1. Ticket mới → `OPEN`
    2. Admin nhận → `IN_PROGRESS` + ghi chú đang xử lý
    3. Đã giải quyết → `RESOLVED` + ghi chú kết quả
    4. Bệnh nhân xác nhận hoặc sau N ngày → `CLOSED`

    **Ví dụ đóng ticket:**
    ```json
    {
      "status": "RESOLVED",
      "response_note": "Đã hỗ trợ đặt lại lịch khám. Lịch hẹn mới: 15/06/2026 09:00"
    }
    ```
    """
    return svc.update_support_request(db, request_id, payload)
