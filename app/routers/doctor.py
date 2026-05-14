from uuid import UUID
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.doctor import (
    DoctorCreate, DoctorUpdate,
    DoctorResponse, DoctorWithSchedules,
    ScheduleCreate, ScheduleUpdate,
    ScheduleResponse,
)
from app.services import doctor_service

# 👉 IMPORT BẢO MẬT
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["2. Clinical - Doctors & Schedules"])


# ──────────────────────────────────────────
# DOCTOR ENDPOINTS
# ──────────────────────────────────────────

@router.get(
    "/doctors",
    response_model=List[DoctorResponse],
    summary="List doctors (filter by department, active, search)",
)
def list_doctors(
    skip         : int            = Query(0,  ge=0),
    limit        : int            = Query(20, ge=1, le=100),
    department_id: Optional[UUID] = Query(None),
    active_only  : bool           = Query(False),
    search       : Optional[str]  = Query(None, description="Search by name or specialization"),
    db           : Session        = Depends(get_db),
    # Public: Không cần Depends auth để Landing Page hiển thị danh sách
):
    return doctor_service.get_doctors(db, skip, limit, department_id, active_only, search)


@router.get(
    "/doctors/{doctor_id}",
    response_model=DoctorWithSchedules,
    summary="Get doctor detail with upcoming schedules",
)
def get_doctor(doctor_id: UUID, db: Session = Depends(get_db)):
    # Public: Không cần Depends auth để bệnh nhân xem profile bác sĩ
    return doctor_service.get_doctor_by_id(db, doctor_id)


@router.post(
    "/doctors",
    response_model=DoctorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new doctor",
)
def create_doctor(
    payload: DoctorCreate, 
    db: Session = Depends(get_db),
    # 🔒 CHỈ ADMIN mới được thêm hồ sơ bác sĩ
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return doctor_service.create_doctor(db, payload)


@router.patch(
    "/doctors/{doctor_id}",
    response_model=DoctorResponse,
    summary="Update doctor information",
)
def update_doctor(
    doctor_id: UUID,
    payload  : DoctorUpdate,
    db       : Session = Depends(get_db),
    # 🔒 ADMIN hoặc chính DOCTOR đó mới được sửa thông tin
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return doctor_service.update_doctor(db, doctor_id, payload)


@router.delete(
    "/doctors/{doctor_id}",
    response_model=DoctorResponse,
    summary="Deactivate a doctor (soft delete)",
)
def deactivate_doctor(
    doctor_id: UUID, 
    db: Session = Depends(get_db),
    # 🔒 CHỈ ADMIN mới có quyền vô hiệu hóa (đuổi việc) bác sĩ
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return doctor_service.deactivate_doctor(db, doctor_id)


# ──────────────────────────────────────────
# SCHEDULE ENDPOINTS
# ──────────────────────────────────────────

@router.get(
    "/schedules",
    response_model=List[ScheduleResponse],
    summary="List schedules (filter by doctor, date, availability)",
)
def list_schedules(
    doctor_id     : Optional[UUID] = Query(None),
    date_filter   : Optional[date] = Query(None, description="Filter by date YYYY-MM-DD"),
    available_only: bool           = Query(False),
    db            : Session        = Depends(get_db),
    # 🔒 Quản lý lịch khám tổng (nhân viên/admin mới được xem toàn bộ)
    current_acc   : Account        = Depends(require_roles("ADMIN"))
):
    return doctor_service.get_schedules(db, doctor_id, date_filter, available_only)


@router.get(
    "/schedules/available",
    response_model=List[dict],
    summary="Get available booking slots for a given date (public-facing)",
)
def get_available_slots(
    date_filter  : date           = Query(..., description="Date to check YYYY-MM-DD"),
    department_id: Optional[UUID] = Query(None),
    db           : Session        = Depends(get_db),
    # Public: Cực kỳ quan trọng để Frontend vẽ màn hình chọn giờ cho Bệnh nhân
):
    return doctor_service.get_available_slots(db, date_filter, department_id)


@router.get(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Get schedule by ID",
)
def get_schedule(
    schedule_id: UUID, 
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account) # 🔒 Chặn 401
):
    return doctor_service.get_schedule_by_id(db, schedule_id)


@router.post(
    "/schedules",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new schedule slot (checks for overlaps & double-booking)",
)
def create_schedule(
    payload: ScheduleCreate, 
    db: Session = Depends(get_db),
    # 🔒 ADMIN, Lễ tân hoặc Bác sĩ được phép tạo lịch
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return doctor_service.create_schedule(db, payload)


@router.patch(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Update schedule (time, room, max patients)",
)
def update_schedule(
    schedule_id: UUID,
    payload    : ScheduleUpdate,
    db         : Session = Depends(get_db),
    # 🔒 ADMIN, Lễ tân hoặc Bác sĩ
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return doctor_service.update_schedule(db, schedule_id, payload)


@router.delete(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Cancel a schedule (only if no bookings exist)",
)
def cancel_schedule(
    schedule_id: UUID, 
    db: Session = Depends(get_db),
    # 🔒 ADMIN, Lễ tân hoặc Bác sĩ
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return doctor_service.cancel_schedule(db, schedule_id)
