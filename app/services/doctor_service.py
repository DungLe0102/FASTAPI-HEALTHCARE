from uuid import UUID
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_
from fastapi import HTTPException, status

from app.models.doctor import Doctor, DoctorSchedule
from app.models.department import Room
from app.schemas.doctor import DoctorCreate, DoctorUpdate, ScheduleCreate, ScheduleUpdate


# ──────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────

def _get_or_404(db: Session, model, pk_col, pk_val, label: str):
    obj = db.query(model).filter(pk_col == pk_val).first()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"{label} '{pk_val}' not found")
    return obj


def _check_room_exists(db: Session, room_id: UUID):
    _get_or_404(db, Room, Room.room_id, room_id, "Room")


# ──────────────────────────────────────────
# DOCTOR SERVICE
# ──────────────────────────────────────────

def get_doctors(
    db          : Session,
    skip        : int = 0,
    limit       : int = 20,
    department_id: Optional[UUID] = None,
    active_only : bool = False,
    search      : Optional[str] = None,
) -> List[Doctor]:
    query = db.query(Doctor)
    if department_id:
        query = query.filter(Doctor.department_id == department_id)
    if active_only:
        query = query.filter(Doctor.is_active == True)
    if search:
        term = f"%{search}%"
        query = query.filter(
            Doctor.last_name.ilike(term) |
            Doctor.first_name.ilike(term) |
            Doctor.specialization.ilike(term)
        )
    return query.order_by(Doctor.last_name).offset(skip).limit(limit).all()


def get_doctor_by_id(db: Session, doctor_id: UUID) -> Doctor:
    return _get_or_404(db, Doctor, Doctor.doctor_id, doctor_id, "Doctor")


def create_doctor(db: Session, payload: DoctorCreate) -> Doctor:
    if payload.department_id:
        from app.services.department_service import get_department_by_id
        get_department_by_id(db, payload.department_id)
    doctor = Doctor(**payload.model_dump())
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


def update_doctor(db: Session, doctor_id: UUID, payload: DoctorUpdate) -> Doctor:
    doctor = get_doctor_by_id(db, doctor_id)
    
    update_data = payload.model_dump(exclude_unset=True)
    if "department_id" in update_data and update_data["department_id"]:
        from app.services.department_service import get_department_by_id
        get_department_by_id(db, update_data["department_id"])

    for field, value in update_data.items():
        setattr(doctor, field, value)
    db.commit()
    db.refresh(doctor)
    return doctor


def deactivate_doctor(db: Session, doctor_id: UUID) -> Doctor:
    """Soft-delete: set is_active=False instead of deleting. Also cancel all future schedules and appointments."""
    doctor = get_doctor_by_id(db, doctor_id)
    doctor.is_active = False

    # 1. Hủy tất cả lịch mở (AVAILABLE) trong tương lai
    now = datetime.now()
    future_schedules = db.query(DoctorSchedule).filter(
        DoctorSchedule.doctor_id == doctor_id,
        DoctorSchedule.start_time > now,
        DoctorSchedule.status == "AVAILABLE"
    ).all()
    for sch in future_schedules:
        sch.status = "CANCELLED"

    # 2. Hủy các cuộc hẹn (SCHEDULED) trong tương lai
    from app.models.appointment import Appointment
    from app.services.appointment_service import update_status
    from app.schemas.appointment import AppointmentStatusUpdate
    future_appointments = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date > now,
        Appointment.status.in_(["SCHEDULED", "PENDING_PAYMENT"])
    ).all()

    for appt in future_appointments:
        if appt.status == "SCHEDULED":
            update_status(db, appt.appointment_id, AppointmentStatusUpdate(status="CANCELLED"))
        elif appt.status == "PENDING_PAYMENT":
            update_status(db, appt.appointment_id, AppointmentStatusUpdate(status="CANCELLED"))

    db.commit()
    db.refresh(doctor)
    return doctor


# ──────────────────────────────────────────
# SCHEDULE SERVICE
# ──────────────────────────────────────────

def _check_overlap(
    db        : Session,
    doctor_id : UUID,
    start_time: datetime,
    end_time  : datetime,
    exclude_id: Optional[UUID] = None,
):
    """
    Kiểm tra chống double-book bác sĩ.
    Một lịch mới bị coi là conflict nếu khoảng thời gian của nó
    giao với bất kỳ lịch nào đang AVAILABLE hoặc FULL.
    """
    query = db.query(DoctorSchedule).filter(
        DoctorSchedule.doctor_id == doctor_id,
        DoctorSchedule.status.in_(["AVAILABLE", "FULL"]),
        and_(
            DoctorSchedule.start_time < end_time,
            DoctorSchedule.end_time   > start_time,
        )
    )
    if exclude_id:
        query = query.filter(DoctorSchedule.schedule_id != exclude_id)

    conflict = query.first()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Doctor already has a schedule from "
                f"{conflict.start_time.strftime('%Y-%m-%d %H:%M')} "
                f"to {conflict.end_time.strftime('%Y-%m-%d %H:%M')}"
            ),
        )


def get_schedules(
    db         : Session,
    doctor_id  : Optional[UUID] = None,
    date_filter: Optional[date] = None,
    available_only: bool = False,
) -> List[DoctorSchedule]:
    query = db.query(DoctorSchedule)
    if doctor_id:
        query = query.filter(DoctorSchedule.doctor_id == doctor_id)
    if date_filter:
        query = query.filter(
            DoctorSchedule.start_time >= datetime.combine(date_filter, datetime.min.time()),
            DoctorSchedule.start_time <  datetime.combine(date_filter, datetime.max.time()),
        )
    if available_only:
        query = query.filter(DoctorSchedule.status == "AVAILABLE")
    return query.order_by(DoctorSchedule.start_time).all()


def get_schedule_by_id(db: Session, schedule_id: UUID) -> DoctorSchedule:
    return _get_or_404(db, DoctorSchedule, DoctorSchedule.schedule_id, schedule_id, "Schedule")


def create_schedule(db: Session, payload: ScheduleCreate) -> DoctorSchedule:
    # Validate doctor + room exist and LOCK doctor to prevent concurrent schedule overlaps
    doctor = db.query(Doctor).filter(Doctor.doctor_id == payload.doctor_id).with_for_update().first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    _check_room_exists(db, payload.room_id)

    # Anti double-booking check (overlap, not just exact start_time)
    _check_overlap(db, payload.doctor_id, payload.start_time, payload.end_time)

    schedule = DoctorSchedule(**payload.model_dump())
    db.add(schedule)
    try:
        db.commit()
        db.refresh(schedule)
    except IntegrityError:
        db.rollback()
        # DB-level unique constraint (exact start_time)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor already has a schedule at this exact start time",
        )
    return schedule


def update_schedule(
    db         : Session,
    schedule_id: UUID,
    payload    : ScheduleUpdate,
) -> DoctorSchedule:
    schedule = get_schedule_by_id(db, schedule_id)
    # LOCK doctor to prevent concurrent schedule overlaps
    doctor = db.query(Doctor).filter(Doctor.doctor_id == schedule.doctor_id).with_for_update().first()

    if schedule.status == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a cancelled schedule",
        )

    update_data = payload.model_dump(exclude_unset=True)

    # Validate new time against existing bookings
    new_start = update_data.get("start_time", schedule.start_time)
    new_end   = update_data.get("end_time",   schedule.end_time)
    if "start_time" in update_data or "end_time" in update_data:
        _check_overlap(db, schedule.doctor_id, new_start, new_end, exclude_id=schedule_id)

    # Validate max_patients not less than current bookings
    new_max = update_data.get("max_patients", schedule.max_patients)
    if new_max < schedule.current_booked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"max_patients ({new_max}) cannot be less than current bookings ({schedule.current_booked})",
        )

    for field, value in update_data.items():
        setattr(schedule, field, value)

    db.commit()
    db.refresh(schedule)
    return schedule


def cancel_schedule(db: Session, schedule_id: UUID) -> DoctorSchedule:
    schedule = db.query(DoctorSchedule).filter(DoctorSchedule.schedule_id == schedule_id).with_for_update().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if schedule.current_booked > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel: {schedule.current_booked} appointment(s) already booked",
        )
    schedule.status = "CANCELLED"
    db.commit()
    db.refresh(schedule)
    return schedule


def get_available_slots(
    db    : Session,
    date_filter: date,
    department_id: Optional[UUID] = None,
) -> List[dict]:
    """
    Trả về danh sách slot còn chỗ cho ngày cụ thể,
    kèm thông tin bác sĩ và phòng — dùng cho trang đặt lịch.
    """
    from sqlalchemy.orm import joinedload
    query = (
        db.query(DoctorSchedule)
        .join(Doctor, DoctorSchedule.doctor_id == Doctor.doctor_id)
        .options(joinedload(DoctorSchedule.doctor))
        .filter(
            DoctorSchedule.status == "AVAILABLE",
            DoctorSchedule.start_time >= datetime.combine(date_filter, datetime.min.time()),
            DoctorSchedule.start_time <  datetime.combine(date_filter, datetime.max.time()),
            Doctor.is_active == True,
        )
    )
    if department_id:
        query = query.filter(Doctor.department_id == department_id)

    schedules = query.order_by(DoctorSchedule.start_time).all()

    return [
        {
            "schedule_id"    : s.schedule_id,
            "doctor_id"      : s.doctor_id,
            "doctor_name"    : f"{s.doctor.last_name} {s.doctor.first_name}",
            "specialization" : s.doctor.specialization,
            "room_id"        : s.room_id,
            "start_time"     : s.start_time,
            "end_time"       : s.end_time,
            "slots_remaining": s.max_patients - s.current_booked,
            "status"         : s.status,
        }
        for s in schedules
    ]