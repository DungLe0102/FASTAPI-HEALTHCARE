"""
Router: Tài chính — Hóa đơn, Thanh toán & Lương bác sĩ
=========================================================
Prefix  : /api/v1
Tags    : 5. Financial - Billing & Payments

Luồng thanh toán thông thường (VietQR):
  1. Lịch hẹn được tạo → hóa đơn tự động sinh ra
  2. POST /billing/{id}/vietqr        → lấy mã QR
  3. Bệnh nhân chuyển khoản theo nội dung QR
  4. Ngân hàng gọi POST /billing/vietqr-webhook → hệ thống xác nhận tự động

Luồng thanh toán thủ công (tiền mặt):
  1. POST /payments                   → tạo giao dịch thủ công
  2. PATCH /payments/{id}/status      → xác nhận đã nhận tiền → status = SUCCESS
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.billing import (
    BillingCreate, BillingResponse,
    PaymentCreate, PaymentStatusUpdate, PaymentResponse,
    VietQRWebhookPayload,
    VietQRRefundRequest, VietQRRefundResponse,
    DoctorPayoutRead, DoctorPayoutCreate,
    DoctorPayoutUpdate, DoctorEarningsCalculate, DoctorEarningsResponse,
)
from app.services import billing_service as svc
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["5. Financial - Billing & Payments"])


# ─────────────────────────────────────────────────────────────
# HÓA ĐƠN (BILLING)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/billing",
    response_model=BillingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Tạo hóa đơn thủ công cho cuộc hẹn",
)
def create_billing(
    payload    : BillingCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Tạo hóa đơn thủ công cho một cuộc hẹn.

    ⚠️ **Thông thường bạn không cần gọi API này.**
    Khi bệnh nhân đặt lịch qua `POST /appointments`, hóa đơn được tạo tự động.

    Chỉ dùng trong trường hợp đặc biệt: nhập dữ liệu từ hệ thống cũ, hoặc sửa hóa đơn bị lỗi.

    - **appointment_id**: UUID cuộc hẹn cần lập hóa đơn
    - **total_amount**: tổng tiền dịch vụ
    - **bhyt_covered_amount**: phần BHYT chi trả (0 nếu không có)
    - **patient_paid_amount**: phần bệnh nhân phải trả (= total - bhyt_covered)
    """
    return svc.create_billing(db, payload)


@router.get(
    "/billing/{billing_id}",
    response_model=BillingResponse,
    summary="Xem chi tiết hóa đơn theo ID",
)
def get_billing(
    billing_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Xem thông tin đầy đủ của một hóa đơn.**

    Response bao gồm:
    - Tổng tiền, phần BHYT chi trả, phần bệnh nhân trả
    - Trạng thái hóa đơn: `UNPAID` / `PARTIAL` / `PAID` / `REFUNDED`
    - Danh sách giao dịch thanh toán đã thực hiện

    Bệnh nhân chỉ được xem hóa đơn của cuộc hẹn của mình.
    """
    bill = svc.get_billing(db, billing_id)
    if current_acc.role == "PATIENT":
        if bill.appointment.patient_id != current_acc.account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return bill


@router.get(
    "/patients/me/invoices",
    response_model=List[BillingResponse],
    summary="[PATIENT] Xem danh sách hóa đơn của bản thân",
)
def list_my_billings(
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("PATIENT")),
):
    """
    **[Chỉ BỆNH NHÂN]** Xem danh sách tất cả hóa đơn của bản thân.
    """
    return svc.list_billings_by_patient(db, current_acc.account_id)


@router.get(
    "/appointments/{appointment_id}/billing",
    response_model=BillingResponse,
    summary="Tìm hóa đơn theo ID cuộc hẹn",
)
def billing_by_appointment(
    appointment_id: UUID,
    db            : Session = Depends(get_db),
    current_acc   : Account = Depends(get_current_account),
):
    """
    **Lấy hóa đơn từ cuộc hẹn thay vì từ billing_id.**

    Tiện dụng hơn `GET /billing/{id}` khi bạn chỉ có `appointment_id`.
    Thường dùng ngay sau khi đặt lịch để lấy hóa đơn và tạo mã QR.

    Bệnh nhân chỉ được xem hóa đơn của cuộc hẹn của mình.
    """
    bill = svc.get_billing_by_appointment(db, appointment_id)
    if current_acc.role == "PATIENT":
        if bill.appointment.patient_id != current_acc.account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return bill


# ─────────────────────────────────────────────────────────────
# GIAO DỊCH THANH TOÁN THỦ CÔNG
# ─────────────────────────────────────────────────────────────

@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Tạo giao dịch thanh toán thủ công (tiền mặt, chuyển khoản)",
)
def create_payment(
    payload    : PaymentCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Ghi nhận giao dịch thanh toán thủ công (lễ tân thu tiền mặt).

    - **billing_id**: UUID hóa đơn cần thanh toán
    - **payment_method**: `CASH` / `BANK_TRANSFER` / `VIETQR`
    - **amount**: số tiền giao dịch

    Sau khi tạo, giao dịch ở trạng thái `PENDING`.
    Dùng `PATCH /payments/{id}/status` để xác nhận đã nhận tiền.
    """
    return svc.create_payment(db, payload)


@router.patch(
    "/payments/{transaction_id}/status",
    response_model=PaymentResponse,
    summary="[ADMIN] Cập nhật trạng thái giao dịch thanh toán thủ công",
)
def update_payment(
    transaction_id: UUID,
    payload       : PaymentStatusUpdate,
    db            : Session = Depends(get_db),
    current_acc   : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Xác nhận hoặc từ chối một giao dịch thanh toán thủ công.

    - **transaction_status**: `SUCCESS` (đã nhận tiền) / `FAILED` (giao dịch thất bại)

    Khi chuyển sang `SUCCESS`, hệ thống tự động:
    1. Cập nhật `billing_status` → `PAID` (nếu đủ tiền)
    2. Chuyển trạng thái cuộc hẹn → `SCHEDULED`
    """
    return svc.update_payment_status(db, transaction_id, payload)


# ─────────────────────────────────────────────────────────────
# THANH TOÁN VIETQR
# ─────────────────────────────────────────────────────────────

@router.post(
    "/billing/{billing_id}/vietqr",
    status_code=status.HTTP_201_CREATED,
    summary="Tạo mã QR thanh toán VietQR cho hóa đơn",
)
def generate_vietqr(
    billing_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Sinh mã QR ngân hàng VietQR để bệnh nhân thanh toán.**

    Trả về URL ảnh mã QR đã tích hợp sẵn số tiền và nội dung chuyển khoản.
    Bệnh nhân chỉ cần mở app ngân hàng, quét mã và xác nhận — không cần nhập gì.

    **Nội dung chuyển khoản** có dạng `PAY <billing_id>` — đây là mã định danh để
    webhook tự động xác nhận thanh toán chính xác.

    ⚠️ Bệnh nhân chỉ được tạo QR cho hóa đơn của chính mình.
    """
    bill = svc.get_billing(db, billing_id)
    if current_acc.role == "PATIENT":
        if bill.appointment.patient_id != current_acc.account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return svc.generate_vietqr_payment(db, billing_id)


@router.post(
    "/billing/vietqr-webhook",
    status_code=status.HTTP_200_OK,
    summary="Webhook nhận thông báo chuyển khoản thành công từ ngân hàng VietQR",
)
def vietqr_webhook(payload: VietQRWebhookPayload, db: Session = Depends(get_db)):
    """
    **Endpoint nhận callback từ ngân hàng khi bệnh nhân chuyển khoản thành công.**

    🔒 **Không yêu cầu JWT** — server ngân hàng gọi đến không có token.
    Bảo mật dựa vào nội dung chuyển khoản chứa mã định danh `PAY <billing_id>`.

    **Dùng để test thủ công (giả lập ngân hàng):**
    ```json
    {
      "error": 0,
      "message": "Giao dịch thành công",
      "data": [
        {
          "amount": 300000,
          "description": "PAY <billing_id>",
          "reference_number": "FT123456789"
        }
      ]
    }
    ```

    **Hệ thống tự động:**
    1. Tìm hóa đơn từ nội dung chuyển khoản
    2. Đối chiếu số tiền
    3. Cập nhật `billing_status` → `PAID`
    4. Chuyển cuộc hẹn → `SCHEDULED`
    5. Gửi thông báo xác nhận cho bệnh nhân
    """
    svc.process_vietqr_webhook(db, payload)
    return {"error": 0, "message": "Webhook xử lý thành công", "data": None}


@router.post(
    "/payments/vietqr-refund",
    response_model=VietQRRefundResponse,
    status_code=status.HTTP_200_OK,
    summary="[ADMIN] Hoàn tiền giao dịch VietQR",
)
def refund_vietqr(
    payload: VietQRRefundRequest,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Thực hiện hoàn tiền cho một giao dịch VietQR đã thanh toán thành công.
    
    Gọi API Refund của VietQR để hoàn lại tiền về tài khoản ngân hàng của bệnh nhân.
    - **transaction_id**: UUID của giao dịch cần hoàn.
    - **amount**: Số tiền cần hoàn.
    - **content**: Nội dung hoàn tiền.
    """
    return svc.refund_vietqr_transaction(
        db, 
        payload
    )


# ─────────────────────────────────────────────────────────────
# QUẢN LÝ LƯƠNG BÁC SĨ (DOCTOR PAYOUT)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/doctor-payouts/calculate-earnings",
    response_model=DoctorEarningsResponse,
    tags=["Financials"],
    summary="[ADMIN] Tính thu nhập dự kiến của bác sĩ theo kỳ",
)
def calculate_earnings(
    payload: DoctorEarningsCalculate,
    db     : Session = Depends(get_db),
    _               = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Tính tổng thu nhập của bác sĩ dựa trên các ca khám đã `COMPLETED`.

    - **doctor_id**: UUID bác sĩ cần tính
    - **period_start / period_end**: khoảng thời gian tính lương (định dạng `YYYY-MM-DD`)

    **Trả về:**
    - Tổng số ca đã hoàn thành
    - Tổng tiền (theo phí tư vấn × số ca)

    Dùng để kiểm tra trước khi tạo lệnh thanh toán `POST /doctor-payouts`.
    Không tạo bản ghi nào — chỉ tính toán và trả về kết quả.
    """
    return svc.calculate_doctor_earnings(db, payload.doctor_id, payload.period_start, payload.period_end)


@router.post(
    "/doctor-payouts",
    response_model=DoctorPayoutRead,
    tags=["Financials"],
    summary="[ADMIN] Lập lệnh thanh toán lương cho bác sĩ",
)
def schedule_payout(
    payload: DoctorPayoutCreate,
    db     : Session = Depends(get_db),
    _               = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Tạo lệnh thanh toán lương cho bác sĩ.

    - **doctor_id**: UUID bác sĩ nhận lương
    - **amount**: số tiền thanh toán (thường lấy từ kết quả `calculate-earnings`)
    - **payout_date**: ngày dự kiến chuyển tiền
    - **period_start / period_end**: kỳ lương tương ứng
    - **notes** *(tùy chọn)*: ghi chú (VD: "Lương tháng 5/2026")

    Lệnh tạo ra ở trạng thái `PENDING`.
    Dùng `PATCH /doctor-payouts/{id}` để chốt khi đã chuyển tiền thực tế.

    **Validation:** Không cho phép tạo 2 lệnh trùng khoảng thời gian cho cùng 1 bác sĩ.
    """
    return svc.create_doctor_payout(db, payload)


@router.get(
    "/doctor-payouts",
    response_model=List[DoctorPayoutRead],
    tags=["Financials"],
    summary="[ADMIN] Danh sách lệnh thanh toán lương",
)
def list_payouts(
    doctor_id: Optional[UUID] = None,
    status   : Optional[str]  = None,
    db       : Session        = Depends(get_db),
    _                         = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Xem tất cả lệnh thanh toán lương, có thể lọc theo bác sĩ hoặc trạng thái.

    - **doctor_id** *(tùy chọn)*: chỉ lấy lệnh của bác sĩ cụ thể
    - **status** *(tùy chọn)*: `PENDING` / `PAID` / `CANCELLED`

    **Ví dụ xem các khoản chưa thanh toán:**
    `GET /doctor-payouts?status=PENDING`
    """
    return svc.list_doctor_payouts(db, doctor_id, status)


@router.patch(
    "/doctor-payouts/{payout_id}",
    response_model=DoctorPayoutRead,
    tags=["Financials"],
    summary="[ADMIN] Cập nhật trạng thái lệnh thanh toán (xác nhận đã trả tiền)",
)
def update_payout(
    payout_id: UUID,
    payload  : DoctorPayoutUpdate,
    db       : Session = Depends(get_db),
    _                  = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Chốt hoặc hủy lệnh thanh toán lương bác sĩ.

    - **status**: `PAID` (đã chuyển tiền thực tế) / `CANCELLED` (hủy lệnh)

    **Khi chuyển sang `PAID`:** ghi nhận ngày thanh toán thực tế.
    **Khi `CANCELLED`:** không thể khôi phục — cần tạo lệnh mới nếu cần.

    **Ví dụ xác nhận đã trả:**
    ```json
    { "status": "PAID" }
    ```
    """
    return svc.update_doctor_payout_status(db, payout_id, payload)
