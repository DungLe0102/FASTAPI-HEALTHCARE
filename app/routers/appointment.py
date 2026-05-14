"""
Router: Lịch hẹn khám
=======================
Prefix  : /api/v1
Tags    : 4. Appointment - Booking & Tracking

Luồng đặt lịch:
  1. GET  /schedules/available      — xem khung giờ còn trống
  2. POST /appointments             — đặt lịch → tự động tạo hóa đơn
  3. POST /billing/{id}/vietqr      — lấy mã QR thanh toán
  4. POST /billing/vietqr-webhook   — giả lập ngân hàng thông báo → trạng thái → SCHEDULED
  5. POST /medical-records          — Admin ghi bệnh án sau khám
  6. PATCH /appointments/{id}/status → COMPLETED

Trạng thái cuộc hẹn (State Machine):
  PENDING_PAYMENT → SCHEDULED → IN_PROGRESS → COMPLETED
                             ↘ CANCELLED  ↗ NO_SHOW
"""

from uuid import UUID
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.appointment import (
    AppointmentCreate, AppointmentStatusUpdate,
    AppointmentResponse, AppointmentDetailResponse, AppointmentListResponse,
)
from app.services import appointment_service
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["4. Appointment - Booking & Tracking"])


# ─────────────────────────────────────────────────────────────
# ĐẶT LỊCH KHÁM
# ─────────────────────────────────────────────────────────────

@router.post(
    "/appointments",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Đặt lịch khám — tự động tạo hóa đơn và mã QR thanh toán",
    description="""
**Luồng tự động khi đặt lịch:**
1. Kiểm tra thẻ BHYT (nếu có `applied_bhyt_id`)
2. Khóa slot khám nguyên tử (tránh race condition — 2 người đặt cùng lúc)
3. Tạo `Billing` record → tính tổng tiền (có hoặc không có BHYT)
4. Trả về `vietqr_url` để bệnh nhân quét mã thanh toán

**Bạn có 10 phút để thanh toán.** Sau đó slot tự động được giải phóng.
""",
)
def book_appointment(
    payload    : AppointmentCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Bệnh nhân đặt lịch khám.**

    - **patient_id**: UUID của bệnh nhân (lấy từ `GET /auth/me`)
    - **schedule_id**: UUID khung giờ khám (lấy từ `GET /schedules/available`)
    - **symptoms** *(tùy chọn)*: mô tả triệu chứng
    - **applied_bhyt_id** *(tùy chọn)*: UUID thẻ BHYT để được giảm phí — thẻ phải `VERIFIED`

    **Response trả về:**
    - `appointment_id`: lưu lại để theo dõi trạng thái
    - `billing_id`: dùng để tạo mã QR (`POST /billing/{id}/vietqr`)
    - `vietqr_url`: URL mã QR sẵn sàng thanh toán

    ⚠️ Bệnh nhân chỉ được đặt lịch cho chính mình.
    """
    if current_acc.role == "PATIENT" and payload.patient_id != current_acc.account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Từ chối: Bệnh nhân chỉ được đặt lịch cho hồ sơ của chính mình",
        )
    return appointment_service.create_appointment(db, payload)


# ─────────────────────────────────────────────────────────────
# XEM THÔNG TIN CUỘC HẸN
# ─────────────────────────────────────────────────────────────

@router.get(
    "/appointments/{appointment_id}",
    response_model=AppointmentDetailResponse,
    summary="Xem chi tiết cuộc hẹn (kèm thông tin bác sĩ và bệnh nhân)",
)
def get_appointment(
    appointment_id: UUID,
    db            : Session = Depends(get_db),
    current_acc   : Account = Depends(get_current_account),
):
    """
    **Xem đầy đủ thông tin một cuộc hẹn cụ thể.**

    Response bao gồm:
    - Thông tin cuộc hẹn (thời gian, trạng thái, triệu chứng)
    - Thông tin bác sĩ và chuyên khoa
    - Thông tin bệnh nhân

    Bệnh nhân chỉ xem được cuộc hẹn của chính mình.
    """
    appt = appointment_service.get_appointment_by_id(db, appointment_id)
    if current_acc.role == "PATIENT" and appt.patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối: Đây không phải cuộc hẹn của bạn")
    return appt


@router.get(
    "/patients/{patient_id}/appointments",
    response_model=AppointmentListResponse,
    summary="Xem lịch sử cuộc hẹn của bệnh nhân",
)
def list_by_patient(
    patient_id   : UUID,
    status_filter: Optional[str] = Query(None, description="Lọc theo trạng thái: PENDING_PAYMENT, SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED, NO_SHOW"),
    skip         : int           = Query(0,  ge=0, description="Bỏ qua N bản ghi"),
    limit        : int           = Query(20, ge=1, le=100, description="Số lượng tối đa"),
    db           : Session       = Depends(get_db),
    current_acc  : Account       = Depends(get_current_account),
):
    """
    **Lấy toàn bộ lịch sử và cuộc hẹn sắp tới của một bệnh nhân.**

    - **status_filter**: lọc theo trạng thái cụ thể (không truyền = lấy tất cả)

    **Ví dụ lấy các lịch đã xác nhận:**
    `GET /patients/{id}/appointments?status_filter=SCHEDULED`

    Bệnh nhân không thể xem lịch sử của người khác.
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối: Không thể xem lịch sử của bệnh nhân khác")
    return appointment_service.get_appointments_by_patient(db, patient_id, status_filter, skip, limit)


@router.get(
    "/doctors/{doctor_id}/appointments",
    response_model=AppointmentListResponse,
    summary="[ADMIN] Xem lịch hẹn của một bác sĩ",
    dependencies=[Depends(require_roles("ADMIN"))],
)
def list_by_doctor(
    doctor_id    : UUID,
    date_filter  : Optional[date] = Query(None, description="Lọc theo ngày cụ thể YYYY-MM-DD"),
    status_filter: Optional[str]  = Query(None, description="Lọc theo trạng thái"),
    skip         : int            = Query(0,   ge=0),
    limit        : int            = Query(50,  ge=1, le=200),
    db           : Session        = Depends(get_db),
):
    """
    **[Chỉ ADMIN]** Xem toàn bộ lịch khám được giao cho một bác sĩ cụ thể.

    Dùng để:
    - Lên kế hoạch phòng khám theo ngày
    - Kiểm tra tải công việc của bác sĩ
    - Tìm cuộc hẹn theo trạng thái cụ thể
    """
    return appointment_service.get_appointments_by_doctor(db, doctor_id, date_filter, status_filter, skip, limit)


@router.get(
    "/appointments/today",
    response_model=AppointmentListResponse,
    summary="[ADMIN] Danh sách cuộc hẹn hôm nay",
    dependencies=[Depends(require_roles("ADMIN"))],
)
def today_appointments(
    doctor_id: Optional[UUID] = Query(None, description="Lọc theo bác sĩ cụ thể (không truyền = toàn phòng khám)"),
    db       : Session        = Depends(get_db),
):
    """
    **[Chỉ ADMIN]** Xem hàng đợi khám bệnh trong ngày hôm nay.

    Dùng cho màn hình lễ tân — hiển thị bệnh nhân cần khám trong ngày.
    Có thể lọc theo bác sĩ để hiển thị riêng từng phòng khám.
    """
    items = appointment_service.get_appointments_today(db, doctor_id)
    return {"total": len(items), "appointments": items}


# ─────────────────────────────────────────────────────────────
# CHUYỂN TRẠNG THÁI CUỘC HẸN
# ─────────────────────────────────────────────────────────────

@router.patch(
    "/appointments/{appointment_id}/status",
    response_model=AppointmentResponse,
    summary="[ADMIN] Chuyển trạng thái cuộc hẹn",
    dependencies=[Depends(require_roles("ADMIN"))],
)
def update_status(
    appointment_id: UUID,
    payload       : AppointmentStatusUpdate,
    db            : Session = Depends(get_db),
):
    """
    **[Chỉ ADMIN]** Thay đổi trạng thái cuộc hẹn theo State Machine.

    **Các chuyển trạng thái hợp lệ:**
    ```
    PENDING_PAYMENT → SCHEDULED     (sau khi thanh toán — thường do webhook tự động)
    SCHEDULED       → IN_PROGRESS   (bệnh nhân đến khám)
    IN_PROGRESS     → COMPLETED     (bác sĩ kết thúc ca khám)
    SCHEDULED       → CANCELLED     (hủy bởi bệnh nhân hoặc phòng khám)
    SCHEDULED       → NO_SHOW       (bệnh nhân không đến)
    ```

    Không thể chuyển ngược trạng thái (VD: `COMPLETED` → `SCHEDULED`).
    Không thể sửa cuộc hẹn đã `CANCELLED` hoặc `NO_SHOW`.

    **Ví dụ:**
    ```json
    { "status": "IN_PROGRESS" }
    ```
    """
    return appointment_service.update_status(db, appointment_id, payload)


# ─────────────────────────────────────────────────────────────
# TÁC VỤ HỆ THỐNG (CRON JOB)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/appointments/mark-no-shows",
    summary="[CRON] Tự động đánh dấu vắng mặt và hủy lịch quá hạn thanh toán",
    dependencies=[Depends(require_roles("ADMIN"))],
)
def mark_no_shows(db: Session = Depends(get_db)):
    """
    **[Tác vụ hệ thống — gọi định kỳ bởi Cron Job]**

    Thực hiện 2 tác vụ dọn dẹp:
    1. **Đánh dấu NO_SHOW**: các cuộc hẹn `SCHEDULED` đã qua giờ hẹn mà không được chuyển sang `IN_PROGRESS`
    2. **Hủy lịch hết hạn**: các cuộc hẹn `PENDING_PAYMENT` đã quá 10 phút mà chưa thanh toán — slot được giải phóng

    **Khuyến nghị:** Thiết lập Cron Job gọi endpoint này mỗi 5 phút:
    ```
    */5 * * * * curl -X POST http://localhost:8000/api/v1/appointments/mark-no-shows -H "Authorization: Bearer <admin_token>"
    ```
    """
    count = appointment_service.mark_no_shows(db)
    return {"detail": f"Dọn dẹp hoàn tất: {count['no_shows']} vắng mặt, {count['cancelled_expired']} hủy do quá hạn thanh toán"}
