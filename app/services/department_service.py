from uuid import UUID
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.department import Department, Room
from app.schemas.department import (
    DepartmentCreate, DepartmentUpdate,
    RoomCreate, RoomUpdate,
)

# ──────────────────────────────────────────
# DEPARTMENT SERVICE
# ──────────────────────────────────────────

def get_all_departments(db: Session, active_only: bool = False) -> List[Department]:
    q = db.query(Department).order_by(Department.department_code)
    if active_only:
        q = q.filter(Department.is_active == True)
    return q.all()


def get_department_by_id(db: Session, department_id: UUID) -> Department:
    dept = db.query(Department).filter(Department.department_id == department_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Department {department_id} not found")
    return dept


def create_department(db: Session, payload: DepartmentCreate) -> Department:
    dept = Department(**payload.model_dump())
    db.add(dept)
    try:
        db.commit()
        db.refresh(dept)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Department code '{payload.department_code}' already exists")
    return dept


def update_department(db: Session, department_id: UUID, payload: DepartmentUpdate) -> Department:
    dept = get_department_by_id(db, department_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dept, field, value)
    try:
        db.commit()
        db.refresh(dept)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update failed: Department code might already be taken")
    return dept


def deactivate_department(db: Session, department_id: UUID) -> Department:
    """Soft delete: set is_active=False. Bảo toàn toàn bộ dữ liệu lịch sử."""
    dept = get_department_by_id(db, department_id)
    if not dept.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department is already inactive")
    dept.is_active = False
    db.commit()
    db.refresh(dept)
    return dept


def reactivate_department(db: Session, department_id: UUID) -> Department:
    dept = get_department_by_id(db, department_id)
    if dept.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department is already active")
    dept.is_active = True
    db.commit()
    db.refresh(dept)
    return dept


def delete_department(db: Session, department_id: UUID) -> dict:
    """Hard delete — chỉ dùng khi chắc chắn không có dữ liệu lịch sử."""
    dept = get_department_by_id(db, department_id)
    active_rooms = db.query(Room).filter(Room.department_id == department_id, Room.is_active == True).count()
    if active_rooms > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete department with active rooms. Deactivate rooms first.")
    try:
        db.delete(dept)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete: department has historical data linked (rooms or doctors)")
    return {"detail": "Department deleted successfully"}


# ──────────────────────────────────────────
# ROOM SERVICE
# ──────────────────────────────────────────

def get_rooms_by_department(db: Session, department_id: UUID, active_only: bool = False) -> List[Room]:
    get_department_by_id(db, department_id)
    query = db.query(Room).filter(Room.department_id == department_id)
    if active_only:
        query = query.filter(Room.is_active == True)
    return query.order_by(Room.room_number).all()


def get_room_by_id(db: Session, room_id: UUID) -> Room:
    room = db.query(Room).filter(Room.room_id == room_id).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Room {room_id} not found")
    return room


def create_room(db: Session, payload: RoomCreate) -> Room:
    get_department_by_id(db, payload.department_id)
    existing_room = db.query(Room).filter(
        Room.department_id == payload.department_id,
        Room.room_number == payload.room_number
    ).first()
    if existing_room:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Room number '{payload.room_number}' already exists in this department")
    room = Room(**payload.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


def update_room(db: Session, room_id: UUID, payload: RoomUpdate) -> Room:
    room = get_room_by_id(db, room_id)
    update_data = payload.model_dump(exclude_unset=True)
    if "room_number" in update_data:
        duplicate = db.query(Room).filter(
            Room.department_id == room.department_id,
            Room.room_number == update_data["room_number"],
            Room.room_id != room_id
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Another room already uses number '{update_data['room_number']}'")
    for field, value in update_data.items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return room


def deactivate_room(db: Session, room_id: UUID) -> Room:
    """Soft delete room: set is_active=False."""
    room = get_room_by_id(db, room_id)
    if not room.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room is already inactive")
    room.is_active = False
    db.commit()
    db.refresh(room)
    return room


def reactivate_room(db: Session, room_id: UUID) -> Room:
    room = get_room_by_id(db, room_id)
    if room.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room is already active")
    room.is_active = True
    db.commit()
    db.refresh(room)
    return room


def delete_room(db: Session, room_id: UUID) -> dict:
    """Hard delete — chỉ dùng khi không có lịch hay hồ sơ liên kết."""
    room = get_room_by_id(db, room_id)
    try:
        db.delete(room)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete: room is linked to existing schedules or medical records")
    return {"detail": "Room deleted successfully"}