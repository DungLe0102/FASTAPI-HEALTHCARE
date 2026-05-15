from uuid import UUID
from datetime import date
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from app.models.account import Account

from app.models.patient import Patient, PatientBHYT, PatientConsent
from app.schemas.patient import (
    PatientCreate, PatientUpdate,
    BHYTCreate, BHYTUpdate, BHYTVerifyUpdate,
    ConsentCreate,
)


# ──────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────

def _get_or_404(db: Session, model, pk_field, pk_value, label: str):
    obj = db.query(model).filter(pk_field == pk_value).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} '{pk_value}' not found"
        )
    return obj


# ──────────────────────────────────────────
# PATIENT SERVICE
# ──────────────────────────────────────────

def get_patients(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
) -> List[Patient]:
    query = db.query(Patient)
    if search:
        term = f"%{search}%"
        query = query.filter(
            Patient.last_name.ilike(term) |
            Patient.first_name.ilike(term) |
            Patient.phone.ilike(term)
        )
    return query.order_by(Patient.created_at.desc()).offset(skip).limit(limit).all()


def get_patient_by_id(db: Session, patient_id: UUID) -> Patient:
    return _get_or_404(db, Patient, Patient.patient_id, patient_id, "Patient")


def create_patient(db: Session, payload: PatientCreate, patient_id: Optional[UUID] = None) -> Patient:
    # 🛑 KIỂM TRA TRỰC TIẾP: Tránh nhầm lẫn IntegrityError với các trường unique khác (như Email/CCCD)
    if payload.phone:
        existing = db.query(Patient).filter(Patient.phone == payload.phone).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Phone number '{payload.phone}' is already registered",
            )
            
    if payload.cccd:
        existing = db.query(Patient).filter(Patient.cccd == payload.cccd).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"CCCD '{payload.cccd}' is already registered",
            )

    data = payload.model_dump()
    if patient_id:
        data["patient_id"] = patient_id
    patient = Patient(**data)
    db.add(patient)
    
    # 🔄 SYNC IDENTITY: Cập nhật full_name bên Account cho đồng bộ
    account = db.query(Account).filter(Account.account_id == patient.patient_id).first()
    if account:
        account.full_name = f"{payload.last_name} {payload.first_name}"

    db.commit()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient_id: UUID, payload: PatientUpdate) -> Patient:
    patient = get_patient_by_id(db, patient_id)
    
    # 🛑 KIỂM TRA TRỰC TIẾP: Đảm bảo số điện thoại mới không bị trùng với người khác
    if payload.phone and payload.phone != patient.phone:
        existing = db.query(Patient).filter(Patient.phone == payload.phone).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number already in use by another patient",
            )

    if payload.cccd and payload.cccd != patient.cccd:
        existing = db.query(Patient).filter(Patient.cccd == payload.cccd).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CCCD already in use by another patient",
            )
            
    if payload.dob and payload.dob >= date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date of birth must be in the past",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
        
    # 🔄 SYNC IDENTITY: Cập nhật full_name bên Account nếu tên thay đổi
    if payload.first_name or payload.last_name:
        account = db.query(Account).filter(Account.account_id == patient.patient_id).first()
        if account:
            account.full_name = f"{patient.last_name} {patient.first_name}"

    db.commit()
    db.refresh(patient)
    return patient


def delete_patient(db: Session, patient_id: UUID) -> dict:
    patient = get_patient_by_id(db, patient_id)
    try:
        db.delete(patient)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete: patient has historical medical records, appointments, or billing data.",
        )
    return {"detail": "Patient deleted successfully"}


# ──────────────────────────────────────────
# BHYT SERVICE
# ──────────────────────────────────────────

def get_bhyt_by_patient(db: Session, patient_id: UUID) -> List[PatientBHYT]:
    get_patient_by_id(db, patient_id)   # ensure patient exists
    return (
        db.query(PatientBHYT)
        .filter(PatientBHYT.patient_id == patient_id)
        .order_by(PatientBHYT.valid_to.desc())
        .all()
    )


def get_active_bhyt(db: Session, patient_id: UUID) -> PatientBHYT:
    """
    Trả về thẻ BHYT đang hoạt động, đã VERIFIED và còn hạn.
    Nếu không có, raise 404 với lý do cụ thể để frontend/admin dễ debug.
    """
    today = date.today()

    # Ưu tiên thẻ đang active; nếu không có thì lấy mới nhất để báo lỗi cụ thể
    latest = (
        db.query(PatientBHYT)
        .filter(PatientBHYT.patient_id == patient_id, PatientBHYT.is_active == True)
        .order_by(PatientBHYT.valid_to.desc())
        .first()
    )
    if not latest:
        latest = (
            db.query(PatientBHYT)
            .filter(PatientBHYT.patient_id == patient_id)
            .order_by(PatientBHYT.valid_to.desc())
            .first()
        )

    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient has no BHYT card on record. Please add one first."
        )
    if not latest.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BHYT card '{latest.bhyt_code}' is deactivated."
        )
    if latest.check_status != "VERIFIED":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"BHYT card '{latest.bhyt_code}' is not yet verified "
                f"(current status: {latest.check_status}). "
                "Please ask Admin to verify via PATCH /bhyt/{id}/verify."
            )
        )
    if latest.valid_to < today:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"BHYT card '{latest.bhyt_code}' expired on "
                f"{latest.valid_to.strftime('%d/%m/%Y')}. Please renew."
            )
        )
    if latest.valid_from > today:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"BHYT card '{latest.bhyt_code}' is not valid yet "
                f"(valid from {latest.valid_from.strftime('%d/%m/%Y')})."
            )
        )

    return latest


def get_latest_bhyt(db: Session, patient_id: UUID) -> Optional[PatientBHYT]:
    """Trả về thẻ BHYT mới nhất bất kể trạng thái — dùng để debug/admin kiểm tra."""
    return (
        db.query(PatientBHYT)
        .filter(PatientBHYT.patient_id == patient_id)
        .order_by(PatientBHYT.valid_to.desc())
        .first()
    )



def create_bhyt(db: Session, payload: BHYTCreate) -> PatientBHYT:
    get_patient_by_id(db, payload.patient_id)

    # 🛑 VALIDATE NGÀY THÁNG: Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc
    if payload.valid_from > payload.valid_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="valid_from date cannot be after valid_to date"
        )
        
    # 🛑 VALIDATE HẠN SỬ DỤNG: Không cho phép nhập thẻ đã quá hạn vào hệ thống
    if payload.valid_to < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add an expired BHYT card"
        )

    # Vô hiệu hóa thẻ cũ (Logic rất tốt)
    db.query(PatientBHYT).filter(
        PatientBHYT.patient_id == payload.patient_id,
        PatientBHYT.is_active == True,
    ).update({"is_active": False})

    bhyt = PatientBHYT(**payload.model_dump())
    db.add(bhyt)
    try:
        db.commit()
        db.refresh(bhyt)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"BHYT code '{payload.bhyt_code}' already exists in the system",
        )
    return bhyt


def update_bhyt(db: Session, bhyt_id: UUID, payload: BHYTUpdate) -> PatientBHYT:
    bhyt = _get_or_404(db, PatientBHYT, PatientBHYT.bhyt_id, bhyt_id, "BHYT")
    
    update_data = payload.model_dump(exclude_unset=True)
    
    # Lấy giá trị mới hoặc giữ nguyên giá trị cũ để so sánh
    new_from = update_data.get("valid_from", bhyt.valid_from)
    new_to   = update_data.get("valid_to", bhyt.valid_to)
    
    # 🛑 VALIDATE NGÀY THÁNG KHI UPDATE
    if new_from and new_to and new_from > new_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="valid_from date cannot be after valid_to date"
        )

    for field, value in update_data.items():
        setattr(bhyt, field, value)
        
    db.commit()
    db.refresh(bhyt)
    return bhyt


def verify_bhyt(db: Session, bhyt_id: UUID, payload: BHYTVerifyUpdate) -> PatientBHYT:
    """Admin / background job updates the portal check result."""
    bhyt = _get_or_404(db, PatientBHYT, PatientBHYT.bhyt_id, bhyt_id, "BHYT")
    bhyt.check_status = payload.check_status
    db.commit()
    db.refresh(bhyt)
    return bhyt


# ──────────────────────────────────────────
# CONSENT SERVICE
# ──────────────────────────────────────────

def get_consents(db: Session, patient_id: UUID) -> List[PatientConsent]:
    get_patient_by_id(db, patient_id)
    return (
        db.query(PatientConsent)
        .filter(PatientConsent.patient_id == patient_id)
        .order_by(PatientConsent.timestamp.desc())
        .all()
    )


def upsert_consent(db: Session, payload: ConsentCreate) -> PatientConsent:
    """
    Per NĐ 13/2023: ghi log mỗi lần thay đổi trạng thái đồng ý.
    Mỗi lần tạo 1 record mới (immutable audit trail).
    """
    get_patient_by_id(db, payload.patient_id)
    consent = PatientConsent(**payload.model_dump())
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent