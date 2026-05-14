from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.department import (
    DepartmentCreate, DepartmentUpdate,
    DepartmentResponse, DepartmentWithRooms,
    RoomCreate, RoomUpdate, RoomResponse,
)
from app.services import department_service

from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["1. Clinical - Setup (Depts & Rooms)"])


# ──────────────────────────────────────────
# DEPARTMENT ENDPOINTS
# ──────────────────────────────────────────

@router.get("/departments", response_model=List[DepartmentResponse], summary="List all departments")
def list_departments(
    active_only: bool = Query(False, description="Filter active departments only"),
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account)
):
    return department_service.get_all_departments(db, active_only)


@router.get("/departments/{department_id}", response_model=DepartmentWithRooms, summary="Get department with its rooms")
def get_department(
    department_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account)
):
    return department_service.get_department_by_id(db, department_id)


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED, summary="Create a new department")
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return department_service.create_department(db, payload)


@router.patch("/departments/{department_id}", response_model=DepartmentResponse, summary="Update department name/code")
def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return department_service.update_department(db, department_id, payload)


@router.delete(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    summary="[ADMIN] Soft-delete department (set is_active=False)",
)
def deactivate_department(
    department_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    """Soft delete — đánh dấu khoa là không còn hoạt động, giữ nguyên dữ liệu lịch sử."""
    return department_service.deactivate_department(db, department_id)


@router.patch(
    "/departments/{department_id}/reactivate",
    response_model=DepartmentResponse,
    summary="[ADMIN] Reactivate a deactivated department",
)
def reactivate_department(
    department_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return department_service.reactivate_department(db, department_id)


# ──────────────────────────────────────────
# ROOM ENDPOINTS
# ──────────────────────────────────────────

@router.get("/departments/{department_id}/rooms", response_model=List[RoomResponse], summary="List rooms by department")
def list_rooms(
    department_id: UUID,
    active_only: bool = Query(False, description="Filter active rooms only"),
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account)
):
    return department_service.get_rooms_by_department(db, department_id, active_only)


@router.get("/rooms/{room_id}", response_model=RoomResponse, summary="Get room by ID")
def get_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account)
):
    return department_service.get_room_by_id(db, room_id)


@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED, summary="Create a new room")
def create_room(
    payload: RoomCreate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return department_service.create_room(db, payload)


@router.patch("/rooms/{room_id}", response_model=RoomResponse, summary="Update room info")
def update_room(
    room_id: UUID,
    payload: RoomUpdate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return department_service.update_room(db, room_id, payload)


@router.delete(
    "/rooms/{room_id}",
    response_model=RoomResponse,
    summary="[ADMIN] Soft-delete room (set is_active=False)",
)
def deactivate_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    """Soft delete — phòng không còn có thể xếp lịch nhưng dữ liệu lịch sử được giữ nguyên."""
    return department_service.deactivate_room(db, room_id)


@router.patch(
    "/rooms/{room_id}/reactivate",
    response_model=RoomResponse,
    summary="[ADMIN] Reactivate a deactivated room",
)
def reactivate_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    return department_service.reactivate_room(db, room_id)
