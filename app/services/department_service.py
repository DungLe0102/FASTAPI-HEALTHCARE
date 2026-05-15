from uuid import UUID
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.department import Department, Room
from app.schemas.department import (
    DepartmentUpdate,
    RoomCreate, RoomUpdate,
)

# ──────────────────────────────────────────
# CHUẨN CƠ CẤU TỔ CHỨC BỆNH VIỆN (BỘ Y TẾ)
# Mỗi entry: (department_code, department_name)
# Mã được đặt tay, đảm bảo duy nhất 100% — không dùng auto-generate nữa
# ──────────────────────────────────────────

HOSPITAL_STANDARDS: dict[str, list[tuple[str, str]]] = {
    "I": [
        # Phòng chức năng
        ("P_KHTH",   "Phòng Kế hoạch tổng hợp"),
        ("P_HCQT",   "Phòng Hành chính quản trị"),
        ("P_TCKT",   "Phòng Tài chính kế toán"),
        ("P_TCCB",   "Phòng Tổ chức cán bộ"),
        ("P_DD",     "Phòng Điều dưỡng"),
        ("P_CDT",    "Phòng Chỉ đạo tuyến"),
        ("P_VTTBYT", "Phòng Vật tư thiết bị y tế"),
        # Khoa lâm sàng
        ("K_KB",     "Khoa Khám bệnh"),
        ("K_HSCC",   "Khoa Hồi sức cấp cứu"),
        ("K_NOITH",  "Khoa Nội tổng hợp"),
        ("K_NOITM",  "Khoa Nội tim mạch"),
        ("K_NOITHS", "Khoa Nội tiêu hóa"),
        ("K_NOITTN", "Khoa Nội thận tiết niệu"),
        ("K_NOIT",   "Khoa Nội tiết"),
        ("K_TN",     "Khoa Truyền nhiễm"),
        ("K_DL",     "Khoa Da liễu"),
        ("K_TK",     "Khoa Thần kinh"),
        ("K_TT",     "Khoa Tâm thần"),
        ("K_YHCT",   "Khoa Y học cổ truyền"),
        ("K_LAO",    "Khoa Lao"),
        ("K_NHI",    "Khoa Nhi"),
        ("K_NGOAITH","Khoa Ngoại tổng hợp"),
        ("K_NGOAITK","Khoa Ngoại thần kinh"),
        ("K_NGOAILN","Khoa Ngoại lồng ngực"),
        ("K_NGOAITHS","Khoa Ngoại tiêu hóa"),
        ("K_NGOAITN","Khoa Ngoại thận tiết niệu"),
        ("K_CTCH",   "Khoa Chấn thương chỉnh hình"),
        ("K_PTGMHS", "Khoa Phẫu thuật gây mê hồi sức"),
        ("K_PS",     "Khoa Phụ sản"),
        ("K_TMH",    "Khoa Tai - mũi - họng"),
        ("K_RHM",    "Khoa Răng - hàm - mặt"),
        ("K_MAT",    "Khoa Mắt"),
        ("K_VLTL",   "Khoa Vật lý trị liệu"),
        # Khoa cận lâm sàng
        ("K_HHTM",   "Khoa Huyết học truyền máu"),
        ("K_HS",     "Khoa Hóa sinh"),
        ("K_VS",     "Khoa Vi sinh"),
        ("K_CDHA",   "Khoa Chẩn đoán hình ảnh"),
        ("K_TDCN",   "Khoa Thăm dò chức năng"),
        ("K_NS",     "Khoa Nội soi"),
        ("K_GPB",    "Khoa Giải phẫu bệnh"),
        ("K_CNK",    "Khoa Chống nhiễm khuẩn"),
        ("K_DUOC",   "Khoa Dược"),
        ("K_DINH",   "Khoa Dinh dưỡng"),
    ],
    "II": [
        ("P_KHTH",   "Phòng Kế hoạch tổng hợp"),
        ("P_HCQT",   "Phòng Hành chính quản trị"),
        ("P_TCKT",   "Phòng Tài chính kế toán"),
        ("K_KB",     "Khoa Khám bệnh"),
        ("K_HSCC",   "Khoa Hồi sức cấp cứu"),
        ("K_NOITH",  "Khoa Nội tổng hợp"),
        ("K_NGOAITH","Khoa Ngoại tổng hợp"),
        ("K_PS",     "Khoa Phụ sản"),
        ("K_NHI",    "Khoa Nhi"),
        ("K_TN",     "Khoa Truyền nhiễm"),
        ("K_DL",     "Khoa Da liễu"),
        ("K_TK",     "Khoa Thần kinh"),
        ("K_YHCT",   "Khoa Y học cổ truyền"),
        ("K_PTGMHS", "Khoa Phẫu thuật gây mê hồi sức"),
        ("K_TMH",    "Khoa Tai - mũi - họng"),
        ("K_RHM",    "Khoa Răng - hàm - mặt"),
        ("K_MAT",    "Khoa Mắt"),
        ("K_CDHA",   "Khoa Chẩn đoán hình ảnh"),
        ("K_HHTM",   "Khoa Huyết học truyền máu"),
        ("K_HS",     "Khoa Hóa sinh"),
        ("K_VS",     "Khoa Vi sinh"),
        ("K_CNK",    "Khoa Chống nhiễm khuẩn"),
        ("K_DUOC",   "Khoa Dược"),
        ("K_DINH",   "Khoa Dinh dưỡng"),
    ],
    "III": [
        ("P_HCQT",   "Phòng Hành chính quản trị"),
        ("P_KHTH",   "Phòng Kế hoạch tổng hợp"),
        ("K_KB",     "Khoa Khám bệnh"),
        ("K_CC",     "Khoa Cấp cứu"),
        ("K_NOI",    "Khoa Nội"),
        ("K_NGOAI",  "Khoa Ngoại"),
        ("K_PS",     "Khoa Phụ sản"),
        ("K_NHI",    "Khoa Nhi"),
        ("K_XNCDHA", "Khoa Xét nghiệm - Chẩn đoán hình ảnh"),
        ("K_DUOC",   "Khoa Dược"),
    ],
}


# ──────────────────────────────────────────
# DEPARTMENT SERVICE
# ──────────────────────────────────────────

def init_standard_departments(db: Session, hospital_class: str) -> List[Department]:
    """
    Tạo danh sách khoa/phòng chuẩn Bộ Y Tế.
    Mã được đặt tay, đảm bảo không bao giờ trùng.
    Idempotent: gọi lại không tạo trùng.
    """
    if hospital_class not in HOSPITAL_STANDARDS:
        raise HTTPException(
            status_code=400,
            detail=f"Hạng bệnh viện không hợp lệ: '{hospital_class}'. Chỉ chấp nhận: I, II, III."
        )

    entries = HOSPITAL_STANDARDS[hospital_class]
    created_depts = []

    for code, name in entries:
        # Idempotent: bỏ qua nếu đã tồn tại
        existing = db.query(Department).filter(Department.department_code == code).first()
        if existing:
            continue

        new_dept = Department(department_code=code, department_name=name)
        db.add(new_dept)
        try:
            db.flush()
            created_depts.append(new_dept)
        except IntegrityError:
            db.rollback()
            continue  # Race condition — bỏ qua

    if created_depts:
        db.commit()
        for d in created_depts:
            db.refresh(d)

    return created_depts


def get_all_departments(db: Session, active_only: bool = False, search: Optional[str] = None) -> List[Department]:
    q = db.query(Department).order_by(Department.department_code)
    if active_only:
        q = q.filter(Department.is_active == True)
    if search:
        term = f"%{search}%"
        q = q.filter(
            Department.department_name.ilike(term) |
            Department.department_code.ilike(term)
        )
    return q.all()


def get_department_by_id(db: Session, department_id: UUID) -> Department:
    dept = db.query(Department).filter(Department.department_id == department_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy khoa/phòng: {department_id}"
        )
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cập nhật thất bại: mã khoa có thể đã bị trùng"
        )
    return dept


def deactivate_department(db: Session, department_id: UUID) -> Department:
    """Soft-delete: đánh dấu is_active=False. Bảo toàn toàn bộ lịch sử."""
    dept = get_department_by_id(db, department_id)
    if not dept.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khoa/phòng này đã ở trạng thái không hoạt động"
        )
    dept.is_active = False
    db.commit()
    db.refresh(dept)
    return dept


def reactivate_department(db: Session, department_id: UUID) -> Department:
    dept = get_department_by_id(db, department_id)
    if dept.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khoa/phòng này đang hoạt động rồi"
        )
    dept.is_active = True
    db.commit()
    db.refresh(dept)
    return dept


def delete_department(db: Session, department_id: UUID) -> dict:
    """Hard delete — chỉ dùng khi chắc chắn không có dữ liệu lịch sử."""
    dept = get_department_by_id(db, department_id)
    active_rooms = db.query(Room).filter(
        Room.department_id == department_id,
        Room.is_active == True
    ).count()
    if active_rooms > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể xóa khoa đang có phòng khám hoạt động. Vô hiệu hóa phòng trước."
        )
    try:
        db.delete(dept)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xóa: khoa đang có dữ liệu lịch sử liên kết (bác sĩ hoặc phòng khám)"
        )
    return {"detail": "Đã xóa khoa/phòng thành công"}


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy phòng khám: {room_id}"
        )
    return room


def create_room(db: Session, payload: RoomCreate) -> Room:
    dept = get_department_by_id(db, payload.department_id)
    if not dept.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tạo phòng khám trong khoa đã bị vô hiệu hóa"
        )
    existing_room = db.query(Room).filter(
        Room.department_id == payload.department_id,
        Room.room_number == payload.room_number
    ).first()
    if existing_room:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Số phòng '{payload.room_number}' đã tồn tại trong khoa này"
        )
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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Số phòng '{update_data['room_number']}' đã được dùng bởi phòng khác"
            )
    for field, value in update_data.items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return room


def deactivate_room(db: Session, room_id: UUID) -> Room:
    """Soft-delete room: set is_active=False."""
    room = get_room_by_id(db, room_id)
    if not room.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phòng này đã ở trạng thái không hoạt động"
        )
    room.is_active = False
    db.commit()
    db.refresh(room)
    return room


def reactivate_room(db: Session, room_id: UUID) -> Room:
    room = get_room_by_id(db, room_id)
    if room.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phòng này đang hoạt động rồi"
        )
    dept = get_department_by_id(db, room.department_id)
    if not dept.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể kích hoạt phòng trong khoa đã bị vô hiệu hóa"
        )
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xóa: phòng đang liên kết với lịch khám hoặc hồ sơ bệnh án"
        )
    return {"detail": "Đã xóa phòng khám thành công"}