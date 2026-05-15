from uuid import UUID
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.appointment import Appointment
from app.models.doctor import DoctorSchedule, Doctor
from app.models.patient import Patient, PatientBHYT
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentStatusUpdate,
    VALID_TRANSITIONS,
)

# ── HELPERS ───────────────────────────────────────

def _get_or_404(db: Session, model, pk_col, pk_val, label: str):
    obj = db.query(model).filter(pk_col == pk_val).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} '{pk_val}' not found",
        )
    return obj

def _get_appointment(db: Session, appointment_id: UUID) -> Appointment:
    # Sử dụng joinedload để lấy kèm thông tin Doctor/Patient tránh lỗi N+1
    return (
        db.query(Appointment)
        .options(
            joinedload(Appointment.doctor),
            joinedload(Appointment.patient),
            joinedload(Appointment.applied_bhyt)
        )
        .filter(Appointment.appointment_id == appointment_id)
        .first()
    ) or _get_or_404(db, Appointment, Appointment.appointment_id, appointment_id, "Appointment")

# ── BOOKING FLOW ──────────────────────────────────

def create_appointment(db: Session, payload: AppointmentCreate) -> Appointment:
    # 1. Lấy schedule và LOCK dòng này để tránh nhiều người đặt cùng lúc 1 slot cuối
    schedule = (
        db.query(DoctorSchedule)
        .filter(DoctorSchedule.schedule_id == payload.schedule_id)
        .with_for_update()  # Ngăn chặn Race Condition
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # 2. KIỂM TRA: Chặn đặt lịch trong quá khứ
    if schedule.start_time < datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot book an appointment in the past",
        )

    # 3. KIỂM TRA: Tình trạng slot
    if schedule.status != "AVAILABLE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Schedule is '{schedule.status}' — no longer available",
        )
    if schedule.current_booked >= schedule.max_patients:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No slots remaining for this schedule",
        )

    # 4. KIỂM TRA: Tránh bệnh nhân đặt 2 lịch trùng một khung giờ (Double Booking)
    duplicate_time = db.query(Appointment).filter(
        Appointment.patient_id == payload.patient_id,
        Appointment.appointment_date == schedule.start_time,
        Appointment.status.in_(["PENDING_PAYMENT", "SCHEDULED", "CHECKED_IN", "IN_PROGRESS"])
    ).first()
    if duplicate_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have another active appointment at this specific time",
        )

    # 5. VALIDATE BHYT (nếu có)
    if payload.applied_bhyt_id:
        bhyt = db.query(PatientBHYT).filter(
            PatientBHYT.bhyt_id    == payload.applied_bhyt_id,
            PatientBHYT.patient_id == payload.patient_id,
        ).first()

        if not bhyt:
            raise HTTPException(status_code=404, detail="BHYT card not found for this patient")
        if not bhyt.is_active or bhyt.check_status != "VERIFIED":
            raise HTTPException(status_code=400, detail="BHYT card is inactive or unverified")
        
        today = date.today()
        if not (bhyt.valid_from <= today <= bhyt.valid_to):
            raise HTTPException(status_code=400, detail="BHYT card is expired")

    # 6. TẠO APPOINTMENT
    appointment = Appointment(
        patient_id       = payload.patient_id,
        doctor_id        = schedule.doctor_id, # Lấy từ schedule để đảm bảo tính nhất quán
        schedule_id      = payload.schedule_id,
        applied_bhyt_id  = payload.applied_bhyt_id,
        appointment_date = schedule.start_time,
        status           = "PENDING_PAYMENT",
        locked_until     = datetime.now() + timedelta(minutes=10)
    )
    db.add(appointment)

    # 7. CẬP NHẬT SLOT TRONG SCHEDULE
    schedule.current_booked += 1
    if schedule.current_booked >= schedule.max_patients:
        schedule.status = "FULL"

    try:
        db.commit()
        db.refresh(appointment)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict detected. Possible duplicate booking.",
        )

    # 8. TỰ ĐỘNG TẠO HÓA ĐƠN & MÃ QR THANH TOÁN
    doctor = db.query(Doctor).filter(Doctor.doctor_id == schedule.doctor_id).first()
    fee = doctor.hourly_consultation_fee if doctor else 0
    
    if fee > 0:
        from app.services import billing_service
        from app.schemas.billing import BillingCreate
        from app.services import notification_service
        
        # Tạo hóa đơn
        bill = billing_service.create_billing(db, BillingCreate(
            appointment_id=appointment.appointment_id,
            total_amount=fee,
            bhyt_covered_amount=0 # Mặc định 0, xử lý logic BHYT riêng nếu cần
        ))
        
        # Sinh mã QR VietQR
        qr_data = billing_service.generate_vietqr_payment(db, bill.billing_id)
        
        # Gắn vào đối tượng trả về
        appointment.billing_id = bill.billing_id
        appointment.payment_qr_url = qr_data["qr_url"]
        
        # Gửi thông báo nhắc thanh toán
        notification_service.create_notification(db, {
            "recipient_id": appointment.patient_id,
            "recipient_type": "PATIENT",
            "title": "Hóa đơn thanh toán cuộc hẹn",
            "content": f"Vui lòng thanh toán hóa đơn {fee} VND qua mã QR để xác nhận cuộc hẹn ngày {appointment.appointment_date.strftime('%d/%m/%Y %H:%M')}. Lịch sẽ tự động hủy sau 10 phút nếu không thanh toán.",
            "notification_type": "PAYMENT"
        })
    else:
        # Nếu miễn phí -> Chốt lịch luôn
        appointment.status = "SCHEDULED"
        appointment.locked_until = None
        db.commit()

    return appointment

# ── STATUS TRANSITIONS ────────────────────────────

def update_status(
    db            : Session,
    appointment_id: UUID,
    payload       : AppointmentStatusUpdate,
) -> Appointment:
    appointment = _get_appointment(db, appointment_id)
    current     = appointment.status
    new_status  = payload.status

    # Kiểm tra State Machine (Validation chuẩn logic luồng)
    allowed = VALID_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from '{current}' to '{new_status}'. Allowed: {allowed}",
        )

    # Khi CANCEL hoặc NO_SHOW: Hoàn trả lại slot cho Schedule
    if new_status in ("CANCELLED", "NO_SHOW") and current in ("PENDING_PAYMENT", "SCHEDULED", "CHECKED_IN"):
        schedule = (
            db.query(DoctorSchedule)
            .filter(DoctorSchedule.schedule_id == appointment.schedule_id)
            .with_for_update()
            .first()
        )
        if schedule and schedule.current_booked > 0:
            schedule.current_booked -= 1
            if schedule.status == "FULL":
                schedule.status = "AVAILABLE"
                
        # NẾU đã thanh toán (SCHEDULED/CHECKED_IN) mà hủy lịch, đánh dấu hóa đơn cần hoàn tiền
        if current in ("SCHEDULED", "CHECKED_IN") and new_status == "CANCELLED":
            from app.models.billing import Billing
            from app.services import notification_service
            bill = db.query(Billing).filter(Billing.appointment_id == appointment.appointment_id).first()
            if bill and bill.billing_status == "PAID":
                bill.billing_status = "REFUND_DUE"
                notification_service.create_notification(db, {
                    "recipient_id": appointment.patient_id,
                    "recipient_type": "PATIENT",
                    "title": "Hủy lịch - Yêu cầu hoàn tiền",
                    "content": f"Cuộc hẹn ngày {appointment.appointment_date.strftime('%d/%m/%Y')} đã được hủy. Hệ thống đã ghi nhận yêu cầu hoàn tiền của bạn.",
                    "notification_type": "SYSTEM_ALERT"
                })

    appointment.status = new_status
    db.commit()
    db.refresh(appointment)
    return appointment

# ── QUERIES ───────────────────────────────────────

def get_appointment_by_id(db: Session, appointment_id: UUID) -> Appointment:
    appt = _get_appointment(db, appointment_id)
    # Mapping thông tin để response schema hiển thị đầy đủ
    appt.doctor_name    = f"{appt.doctor.last_name} {appt.doctor.first_name}"
    appt.patient_name   = f"{appt.patient.last_name} {appt.patient.first_name}"
    appt.specialization = appt.doctor.specialization
    appt.bhyt_code      = appt.applied_bhyt.bhyt_code if appt.applied_bhyt else None
    return appt

def mark_no_shows(db: Session) -> dict:
    """
    CRON JOB: Quét các lịch SCHEDULED đã quá giờ hẹn 30 phút mà chưa CHECK_IN
              và tự động CANCEL các lịch PENDING_PAYMENT đã hết hạn giữ chỗ.
    """
    limit_time = datetime.now() - timedelta(minutes=30)
    now = datetime.now()
    
    # 1. Quét SCHEDULED -> NO_SHOW
    appointments = db.query(Appointment).filter(
        Appointment.status == "SCHEDULED",
        Appointment.appointment_date < limit_time,
    ).all()

    count_no_show = 0
    for appt in appointments:
        # Tái sử dụng logic update_status để hoàn trả slot tự động
        update_status(db, appt.appointment_id, AppointmentStatusUpdate(status="NO_SHOW"))
        count_no_show += 1

    # 2. Quét PENDING_PAYMENT -> CANCELLED
    expired_payments = db.query(Appointment).filter(
        Appointment.status == "PENDING_PAYMENT",
        Appointment.locked_until < now,
    ).all()
    
    count_cancelled = 0
    for appt in expired_payments:
        update_status(db, appt.appointment_id, AppointmentStatusUpdate(status="CANCELLED"))
        count_cancelled += 1

    return {"no_shows": count_no_show, "cancelled_expired": count_cancelled}

def get_appointments_by_patient(
    db: Session,
    patient_id: UUID,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> dict:
    """Danh sách cuộc hẹn của một bệnh nhân (phân trang, lọc status)."""
    _get_or_404(db, Patient, Patient.patient_id, patient_id, "Patient")

    query = db.query(Appointment).filter(Appointment.patient_id == patient_id)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)

    total = query.count()
    appointments = (
        query.order_by(Appointment.appointment_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "appointments": appointments}


def get_appointments_by_doctor(
    db: Session,
    doctor_id: UUID,
    date_filter: Optional[date] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    """Danh sách cuộc hẹn của một bác sĩ (lọc theo ngày / status)."""
    _get_or_404(db, Doctor, Doctor.doctor_id, doctor_id, "Doctor")

    query = db.query(Appointment).filter(Appointment.doctor_id == doctor_id)
    if date_filter:
        day_start = datetime.combine(date_filter, datetime.min.time())
        day_end = datetime.combine(date_filter, datetime.max.time())
        query = query.filter(
            Appointment.appointment_date >= day_start,
            Appointment.appointment_date <= day_end,
        )
    if status_filter:
        query = query.filter(Appointment.status == status_filter)

    total = query.count()
    appointments = (
        query.order_by(Appointment.appointment_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "appointments": appointments}


def get_appointments_today(db: Session, doctor_id: Optional[UUID] = None) -> List[Appointment]:
    today = date.today()
    query = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor)
    ).filter(
        Appointment.appointment_date >= datetime.combine(today, datetime.min.time()),
        Appointment.appointment_date <= datetime.combine(today, datetime.max.time()),
        Appointment.status.in_(["PENDING_PAYMENT", "SCHEDULED", "CHECKED_IN", "IN_PROGRESS"]),
    )
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    
    return query.order_by(Appointment.appointment_date).all()