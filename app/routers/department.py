from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.department import (
    DepartmentUpdate, DepartmentResponse, DepartmentWithRooms,
    RoomCreate, RoomUpdate, RoomResponse,
)
from app.services import department_service
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["1. Setup - Khoa & Phòng"])


# ──────────────────────────────────────────
# DEPARTMENT ENDPOINTS
# Cách TẠO khoa DUY NHẤT là qua init-standard (Chuẩn Bộ Y Tế)
# Không còn POST /departments thủ công nữa — đảm bảo tính nhất quán
# ──────────────────────────────────────────

@router.post(
    "/departments/init-standard/{hospital_class}",
    response_model=List[DepartmentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Khởi tạo khoa/phòng chuẩn Bộ Y Tế theo hạng bệnh viện (I, II, III)",
)
def init_standard_departments(
    hospital_class: str,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN"))
):
    """
    Nguồn tạo khoa DUY NHẤT trong hệ thống.
    Tự động sinh danh sách khoa/phòng chuẩn theo Thông tư Bộ Y Tế.
    - Hạng I: Bệnh viện đa khoa lớn (~18 khoa/phòng)
    - Hạng II: Bệnh viện đa khoa tỉnh (~12 khoa/phòng)
    - Hạng III: Bệnh viện cơ sở, trung tâm y tế (~8 khoa/phòng)
    Nếu khoa đã tồn tại (trùng mã), hệ thống bỏ qua, không tạo trùng.
    """
    return department_service.init_standard_departments(db, hospital_class.upper())


@router.get(
    "/departments",
    response_model=List[DepartmentResponse],
    summary="Danh sách toàn bộ khoa/phòng",
)
def list_departments(
    active_only: bool = Query(False, description="Chỉ lấy các khoa đang hoạt động"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên hoặc mã khoa"),
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    return department_service.get_all_departments(db, active_only, search)


@router.get(
    "/departments/{department_id}",
    response_model=DepartmentWithRooms,
    summary="Chi tiết khoa và danh sách phòng khám",
)
def get_department(
    department_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    return department_service.get_department_by_id(db, department_id)


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    summary="[ADMIN] Cập nhật tên khoa/phòng",
)
def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """Chỉ cho phép đổi tên hiển thị (department_name). Mã khoa không được thay đổi."""
    return department_service.update_department(db, department_id, payload)


@router.delete(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    summary="[ADMIN] Vô hiệu hóa khoa (Soft-delete)",
)
def deactivate_department(
    department_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    Soft-delete: đánh dấu khoa là ngừng hoạt động (is_active=False).
    Toàn bộ lịch sử khám bệnh, bác sĩ, phòng khám liên quan được bảo toàn.
    Hệ thống sẽ chặn tạo phòng mới trong khoa đã bị vô hiệu hóa.
    """
    return department_service.deactivate_department(db, department_id)


@router.patch(
    "/departments/{department_id}/reactivate",
    response_model=DepartmentResponse,
    summary="[ADMIN] Kích hoạt lại khoa đã vô hiệu hóa",
)
def reactivate_department(
    department_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    return department_service.reactivate_department(db, department_id)


# ──────────────────────────────────────────
# ROOM ENDPOINTS
# ──────────────────────────────────────────

@router.get(
    "/departments/{department_id}/rooms",
    response_model=List[RoomResponse],
    summary="Danh sách phòng khám theo khoa",
)
def list_rooms(
    department_id: UUID,
    active_only: bool = Query(False, description="Chỉ lấy phòng đang hoạt động"),
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    return department_service.get_rooms_by_department(db, department_id, active_only)


@router.get(
    "/rooms/{room_id}",
    response_model=RoomResponse,
    summary="Chi tiết phòng khám",
)
def get_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    return department_service.get_room_by_id(db, room_id)


@router.post(
    "/departments/{department_id}/rooms",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Thêm phòng khám vào khoa",
)
def create_room(
    department_id: UUID,
    payload: RoomCreate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    Tạo phòng khám mới gắn với một khoa cụ thể.
    department_id lấy từ URL, không cần truyền trong body.
    """
    payload.department_id = department_id
    return department_service.create_room(db, payload)


@router.patch(
    "/rooms/{room_id}",
    response_model=RoomResponse,
    summary="[ADMIN] Cập nhật thông tin phòng khám",
)
def update_room(
    room_id: UUID,
    payload: RoomUpdate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    return department_service.update_room(db, room_id, payload)


@router.delete(
    "/rooms/{room_id}",
    response_model=RoomResponse,
    summary="[ADMIN] Vô hiệu hóa phòng khám (Soft-delete)",
)
def deactivate_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """Soft-delete: phòng không còn được xếp lịch, lịch sử được giữ nguyên."""
    return department_service.deactivate_room(db, room_id)


@router.patch(
    "/rooms/{room_id}/reactivate",
    response_model=RoomResponse,
    summary="[ADMIN] Kích hoạt lại phòng khám đã vô hiệu hóa",
)
def reactivate_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    return department_service.reactivate_room(db, room_id)
