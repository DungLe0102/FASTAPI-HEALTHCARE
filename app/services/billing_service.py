from decimal import Decimal
from datetime import datetime, date
from uuid import UUID
import re
import requests
import hashlib
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.config import settings

from app.models.billing import Billing, PaymentTransaction, DoctorPayout
from app.models.appointment import Appointment
from app.models.patient import PatientBHYT
from app.models.doctor import Doctor
from sqlalchemy import func
from app.schemas.billing import (
    BillingCreate, 
    PaymentCreate, 
    PaymentStatusUpdate, 
    VietQRWebhookPayload,
    DoctorPayoutCreate,
    DoctorPayoutUpdate
)
from app.services import notification_service 

# ── HELPERS ───────────────────────────────────────

def _404(db: Session, model, col, val, label: str):
    obj = db.query(model).filter(col == val).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"{label} '{val}' not found"
        )
    return obj

# ── BILLING CORE ──────────────────────────────────

def create_billing(db: Session, payload: BillingCreate) -> Billing:
    appt = _404(db, Appointment, Appointment.appointment_id, payload.appointment_id, "Appointment")
    
    # Chỉ cho phép tạo hóa đơn nếu đang chờ thanh toán hoặc đã khám xong
    if appt.status not in ["COMPLETED", "PENDING_PAYMENT"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Cannot bill for appointment status: {appt.status}"
        )

    # Chống tạo trùng hóa đơn
    existing = db.query(Billing).filter(Billing.appointment_id == payload.appointment_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail="Billing already exists for this appointment"
        )

    if payload.bhyt_covered_amount > payload.total_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BHYT covered amount cannot exceed total amount"
        )

    bill = Billing(
        appointment_id      = payload.appointment_id,
        total_amount        = payload.total_amount,
        bhyt_covered_amount = payload.bhyt_covered_amount,
        patient_paid_amount = payload.total_amount - payload.bhyt_covered_amount, # Auto-calc
        billing_status      = "UNPAID",
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill

def get_billing(db: Session, billing_id: UUID) -> Billing:
    return _404(db, Billing, Billing.billing_id, billing_id, "Billing")

def get_billing_by_appointment(db: Session, appointment_id: UUID) -> Billing:
    bill = db.query(Billing).filter(Billing.appointment_id == appointment_id).first()
    if not bill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No billing found for this appointment",
        )
    return bill

# ── PAYMENT & TRANSACTIONS ────────────────────────

def create_payment(db: Session, payload: PaymentCreate) -> PaymentTransaction:
    bill = get_billing(db, payload.billing_id)
    if bill.billing_status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bill is already fully paid",
        )
    if payload.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount must be greater than 0",
        )

    txn = PaymentTransaction(
        billing_id           = payload.billing_id,
        payment_method       = payload.payment_method,
        amount               = payload.amount,
        gateway_reference_id = payload.gateway_reference_id,
        transaction_status   = "PENDING",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn

def update_payment_status(db: Session, transaction_id: UUID, payload: PaymentStatusUpdate) -> PaymentTransaction:
    # Sử dụng with_for_update() để khóa dòng này, tránh Webhook gọi trùng lặp
    txn = db.query(PaymentTransaction).filter(
        PaymentTransaction.transaction_id == transaction_id
    ).with_for_update().first()

    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    if txn.transaction_status != "PENDING":
        return txn # Nếu đã xử lý rồi thì trả về luôn, không báo lỗi để Webhook không gửi lại

    txn.transaction_status   = payload.transaction_status
    txn.gateway_reference_id = payload.gateway_reference_id or txn.gateway_reference_id
    txn.payment_date         = datetime.now()

    if payload.transaction_status == "SUCCESS":
        bill = get_billing(db, txn.billing_id)
        # Tính toán tổng tiền đã thanh toán thành công.
        # Lưu ý: t.amount của txn hiện tại đã được tính trong bill.transactions do session identity map.
        paid_total = sum(
            t.amount for t in bill.transactions 
            if t.transaction_status == "SUCCESS"
        )

        if paid_total >= bill.patient_paid_amount:
            bill.billing_status = "PAID"
            
            # Cập nhật trạng thái Appointment và BHYT
            appt = _404(db, Appointment, Appointment.appointment_id, bill.appointment_id, "Appointment")
            if appt.status == "PENDING_PAYMENT":
                appt.status = "SCHEDULED"
                appt.locked_until = None
            elif appt.status in ("CANCELLED", "NO_SHOW"):
                # Thanh toán đến muộn sau khi lịch đã bị hủy (hết 10 phút)!
                from app.models.doctor import DoctorSchedule
                schedule = db.query(DoctorSchedule).filter(DoctorSchedule.schedule_id == appt.schedule_id).with_for_update().first()
                if schedule and schedule.current_booked < schedule.max_patients:
                    # Khôi phục lịch thành công do slot vẫn trống
                    schedule.current_booked += 1
                    if schedule.current_booked >= schedule.max_patients:
                        schedule.status = "FULL"
                    appt.status = "SCHEDULED"
                    appt.locked_until = None
                else:
                    # Lịch đã bị người khác đặt mất (FULL)
                    bill.billing_status = "REFUND_DUE"
                    notification_service.create_notification(db, {
                        "recipient_id": appt.patient_id,
                        "recipient_type": "PATIENT",
                        "title": "Thanh toán thành công nhưng lịch đã đầy",
                        "content": f"Hệ thống nhận được thanh toán nhưng cuộc hẹn ngày {appt.appointment_date.strftime('%d/%m/%Y')} đã nhường cho người khác do quá hạn giữ chỗ. Vui lòng liên hệ quầy tiếp đón để được hoàn tiền hoặc đổi lịch.",
                        "notification_type": "SYSTEM_ALERT"
                    })
            
            if appt.applied_bhyt_id:
                bhyt = db.query(PatientBHYT).filter(PatientBHYT.bhyt_id == appt.applied_bhyt_id).first()
                if bhyt:
                    bhyt.last_extension_date = date.today()
                    bhyt.check_status = "VERIFIED"
        else:
            bill.billing_status = "PARTIAL"

    db.commit()
    db.refresh(txn)
    return txn

# ── VIETQR LOGIC ──────────────────────────────────

def generate_vietqr_payment(db: Session, billing_id: UUID) -> dict:
    bill = get_billing(db, billing_id)
    
    # Nếu hóa đơn đã trả xong thì không sinh thêm QR/transaction mới
    if bill.billing_status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bill is already fully paid",
        )

    # Idempotent: nếu đã có 1 transaction VIETQR đang chờ (PENDING) cho cùng hóa đơn,
    # thì tái sử dụng để tránh tạo nhiều "luồng" thanh toán song song khi người dùng bấm/scan lại.
    existing_txn = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.billing_id == billing_id,
            PaymentTransaction.payment_method == "VIETQR",
            PaymentTransaction.transaction_status == "PENDING",
        )
        .order_by(PaymentTransaction.transaction_id.desc())
        .first()
    )

    txn = existing_txn
    if not txn:
        # Tạo transaction để quản lý việc quét mã
        txn = create_payment(
            db,
            PaymentCreate(
                billing_id=billing_id,
                payment_method="VIETQR",
                amount=bill.patient_paid_amount,
            ),
        )

    # Nội dung chuyển khoản: PAY <UUID>
    transfer_content = f"PAY {txn.transaction_id}"

    # Cập nhật Link VietQR theo yêu cầu của bạn (HDBank)
    # Thêm tham số động amount và addInfo để ngân hàng tự điền nội dung cho khách
    base_url = "https://img.vietqr.io/image/HDB-107704070005803-print.png"
    qr_url = f"{base_url}?amount={int(txn.amount)}&addInfo={transfer_content}"

    return {
        "transaction_id": txn.transaction_id,
        "qr_url": qr_url,
        "amount": txn.amount,
        "transfer_content": transfer_content
    }

def process_vietqr_webhook(db: Session, payload: VietQRWebhookPayload):
    """Xử lý Callback từ VietQR: Xác nhận tiền -> Chốt lịch -> Thông báo"""
    for item in payload.data:
        # 1. Trích xuất transaction_id từ nội dung chuyển khoản bằng Regex
        match = re.search(r"PAY\s+([a-fA-F0-9\-]{36})", item.description)
        if not match:
            continue
        try:
            txn_id = UUID(match.group(1))
        except ValueError:
            continue

        # 2. Kiểm tra số tiền chuyển khoản có khớp/đủ không
        # (Lưu ý: item.amount là số tiền thực tế ngân hàng nhận được)
        txn = db.query(PaymentTransaction).filter(
            PaymentTransaction.transaction_id == txn_id
        ).first()

        if not txn or txn.transaction_status != "PENDING":
            continue

        if Decimal(str(item.amount)) < txn.amount:
            # Nếu chuyển thiếu tiền, đánh dấu thất bại hoặc xử lý riêng
            update_payment_status(db, txn_id, PaymentStatusUpdate(transaction_status="FAILED"))
            continue

        # 3. Cập nhật trạng thái Payment SUCCESS (Đã bao gồm cập nhật Appointment/BHYT bên trong)
        update_payment_status(db, txn_id, PaymentStatusUpdate(
            transaction_status="SUCCESS",
            gateway_reference_id=item.reference_number
        ))
        
        # 4. Gửi thông báo tự động cho bệnh nhân
        bill = get_billing(db, txn.billing_id)
        appt = _404(db, Appointment, Appointment.appointment_id, bill.appointment_id, "Appointment")
        notification_service.create_notification(db, {
            "recipient_id": appt.patient_id,
            "recipient_type": "PATIENT",
            "title": "Thanh toán thành công",
            "content": f"Hóa đơn cho cuộc hẹn ngày {appt.appointment_date.strftime('%d/%m/%Y')} đã được xác nhận.",
            "notification_type": "PAYMENT"
        })

def check_vietqr_transaction(db: Session, transaction_id: UUID) -> dict:
    """Gọi API Check Transaction của VietQR"""
    txn = _404(db, PaymentTransaction, PaymentTransaction.transaction_id, transaction_id, "Transaction")
    if not txn.gateway_reference_id:
        raise HTTPException(status_code=400, detail="Transaction has no gateway reference id")
    
    val = txn.gateway_reference_id
    raw_str = f"{settings.VIETQR_ACCOUNT_NO}{settings.VIETQR_USERNAME}"
    checksum = hashlib.md5(raw_str.encode('utf-8')).hexdigest()

    payload = {
        "bankAccount": settings.VIETQR_ACCOUNT_NO,
        "type": "1", # Check by referenceNumber
        "value": val,
        "checkSum": checksum
    }

    headers = {
        "Content-Type": "application/json",
        # Lưu ý: Token theo tài liệu VietQR là từ API Get Token, ở đây ta dùng API_KEY hoặc cấu hình tùy hệ thống.
        "Authorization": f"Bearer {settings.VIETQR_API_KEY}"
    }

    try:
        res = requests.post(
            f"{settings.VIETQR_HOST}/vqr/api/transactions/check-order",
            json=payload,
            headers=headers,
            timeout=10
        )
        data = res.json()
        if res.status_code == 200:
            return data # Có thể là mảng theo document
        else:
            raise HTTPException(status_code=400, detail=f"VietQR Check Failed: {data.get('message', 'Unknown Error')}")
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"VietQR API Error: {str(e)}")

def refund_vietqr_transaction(db: Session, transaction_id: UUID, amount: Decimal, content: str) -> dict:
    """Gọi API Refund của VietQR"""
    txn = _404(db, PaymentTransaction, PaymentTransaction.transaction_id, transaction_id, "Transaction")
    if txn.transaction_status != "SUCCESS":
        raise HTTPException(status_code=400, detail="Can only refund SUCCESS transactions")
    if not txn.gateway_reference_id:
        raise HTTPException(status_code=400, detail="Transaction has no gateway reference id")

    # 1. Gọi check-order (tùy chọn nhưng khuyến nghị)
    check_vietqr_transaction(db, transaction_id)

    # 2. Tạo Checksum cho API Refund
    amount_str = str(int(amount)) # Thường amount là chuỗi số nguyên
    raw_str = f"{settings.VIETQR_SECRET_KEY}{txn.gateway_reference_id}{amount_str}{settings.VIETQR_ACCOUNT_NO}"
    checksum = hashlib.md5(raw_str.encode('utf-8')).hexdigest()

    payload = {
        "bankCode": settings.VIETQR_BANK_ID,
        "bankAccount": settings.VIETQR_ACCOUNT_NO,
        "referenceNumber": txn.gateway_reference_id,
        "amount": amount_str,
        "content": content,
        "checkSum": checksum
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.VIETQR_API_KEY}"
    }

    try:
        res = requests.post(
            f"{settings.VIETQR_HOST}/vqr/api/transaction/refund",
            json=payload,
            headers=headers,
            timeout=10
        )
        data = res.json()
        if res.status_code == 200 and data.get("status") == "SUCCESS":
            # Cập nhật trạng thái transaction thành REFUNDED
            txn.transaction_status = "REFUNDED"
            db.commit()
            
            # Cập nhật lại trạng thái hóa đơn
            bill = get_billing(db, txn.billing_id)
            paid_total = sum(
                t.amount for t in bill.transactions 
                if t.transaction_status == "SUCCESS"
            )

            if paid_total >= bill.patient_paid_amount:
                bill.billing_status = "PAID"
            elif paid_total > 0:
                bill.billing_status = "PARTIAL"
            else:
                bill.billing_status = "UNPAID"
            db.commit()
            
            return {
                "status": "SUCCESS",
                "message": data.get("message", "Refund successful")
            }
        else:
            raise HTTPException(status_code=400, detail=f"VietQR Refund Failed: {data.get('message', 'Unknown Error')}")
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"VietQR API Error: {str(e)}")



# ── DOCTOR PAYOUT LOGIC ───────────────────────────

def check_overlapping_payout(db: Session, doctor_id: UUID, start_date: date, end_date: date, exclude_payout_id: UUID = None):
    """
    Kiểm tra xem bác sĩ đã có bản ghi thanh toán nào (PENDING hoặc PAID) trong khoảng thời gian bị trùng lặp chưa.
    """
    query = db.query(DoctorPayout).filter(
        DoctorPayout.doctor_id == doctor_id,
        DoctorPayout.status.in_(["PENDING", "PAID"]),
        # Điều kiện overlap: (StartA <= EndB) and (EndA >= StartB)
        DoctorPayout.period_start <= end_date,
        DoctorPayout.period_end >= start_date
    )
    if exclude_payout_id:
        query = query.filter(DoctorPayout.payout_id != exclude_payout_id)
        
    overlap = query.first()
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Doctor already has a {overlap.status} payout for period {overlap.period_start} to {overlap.period_end} which overlaps with this request."
        )


def calculate_doctor_earnings(db: Session, doctor_id: UUID, start_date: date, end_date: date) -> dict:
    """
    Tính toán tổng thu nhập của bác sĩ dựa trên các cuộc hẹn đã hoàn thành trong khoảng thời gian.
    """
    doctor = _404(db, Doctor, Doctor.doctor_id, doctor_id, "Doctor")
    
    # Lấy các cuộc hẹn COMPLETED trong khoảng thời gian
    completed_appointments = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status == "COMPLETED",
        func.date(Appointment.appointment_date) >= start_date,
        func.date(Appointment.appointment_date) <= end_date
    ).all()

    total_count = len(completed_appointments)
    total_earnings = total_count * doctor.hourly_consultation_fee

    return {
        "doctor_id": doctor_id,
        "doctor_name": f"{doctor.first_name} {doctor.last_name}",
        "period_start": start_date,
        "period_end": end_date,
        "completed_appointments": total_count,
        "total_earnings": total_earnings
    }


def create_doctor_payout(db: Session, payload: DoctorPayoutCreate) -> DoctorPayout:
    _404(db, Doctor, Doctor.doctor_id, payload.doctor_id, "Doctor")
    
    # Kiểm tra trùng lặp kỳ thanh toán
    check_overlapping_payout(db, payload.doctor_id, payload.period_start, payload.period_end)
    
    payout = DoctorPayout(
        doctor_id    = payload.doctor_id,
        amount       = payload.amount,
        payout_date  = payload.payout_date,
        period_start = payload.period_start,
        period_end   = payload.period_end,
        notes        = payload.notes,
        status       = "PENDING"
    )
    db.add(payout)
    db.commit()
    db.refresh(payout)
    return payout


def list_doctor_payouts(db: Session, doctor_id: UUID = None, status: str = None):
    query = db.query(DoctorPayout)
    if doctor_id:
        query = query.filter(DoctorPayout.doctor_id == doctor_id)
    if status:
        query = query.filter(DoctorPayout.status == status)
    return query.order_by(DoctorPayout.payout_date.desc()).all()


def update_doctor_payout_status(db: Session, payout_id: UUID, payload: DoctorPayoutUpdate) -> DoctorPayout:
    payout = _404(db, DoctorPayout, DoctorPayout.payout_id, payout_id, "Payout")
    
    payout.status = payload.status
    if payload.notes:
        payout.notes = payload.notes
        
    db.commit()
    db.refresh(payout)
    return payout
