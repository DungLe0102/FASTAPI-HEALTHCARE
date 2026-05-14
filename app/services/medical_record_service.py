from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import hashlib

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.medical_record import MedicalRecord, ClinicalService, RecordService
from app.models.appointment import Appointment
from app.schemas.medical_record import (
    MedicalRecordCreate, MedicalRecordUpdate,
    ClinicalServiceCreate, ClinicalServiceUpdate,
    RecordServiceCreate, SignRecordRequest,
)


# ──────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────

def _get_or_404(db: Session, model, pk_col, pk_val, label: str):
    obj = db.query(model).filter(pk_col == pk_val).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"{label} '{pk_val}' not found"
        )
    return obj


def _resolve_price(db: Session, item: RecordServiceCreate) -> Decimal:
    """Dùng actual_price từ payload nếu có, nếu không lấy giá từ danh mục."""
    if item.actual_price is not None:
        return item.actual_price
    
    svc = _get_or_404(db, ClinicalService, ClinicalService.service_id, item.service_id, "ClinicalService")
    
    # 🛑 Validation: Không cho phép sử dụng dịch vụ đã ngừng hoạt động
    if not svc.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service '{svc.service_name}' is currently inactive"
        )
    return svc.price


# ──────────────────────────────────────────
# CLINICAL SERVICE (Danh mục dịch vụ)
# ──────────────────────────────────────────

def list_services(
    db          : Session,
    active_only : bool = True,
    bhyt_only   : bool = False,
    search      : Optional[str] = None,
) -> List[ClinicalService]:
    q = db.query(ClinicalService)
    if active_only:
        q = q.filter(ClinicalService.is_active == True)
    if bhyt_only:
        q = q.filter(ClinicalService.is_bhyt_covered == True)
    if search:
        term = f"%{search}%"
        q = q.filter(
            ClinicalService.service_name.ilike(term) |
            ClinicalService.service_code.ilike(term)
        )
    return q.order_by(ClinicalService.service_code).all()


def get_service(db: Session, service_id: UUID) -> ClinicalService:
    return _get_or_404(db, ClinicalService, ClinicalService.service_id, service_id, "ClinicalService")


def create_service(db: Session, payload: ClinicalServiceCreate) -> ClinicalService:
    svc = ClinicalService(**payload.model_dump())
    db.add(svc)
    try:
        db.commit()
        db.refresh(svc)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service code '{payload.service_code}' already exists"
        )
    return svc


def update_service(db: Session, service_id: UUID, payload: ClinicalServiceUpdate) -> ClinicalService:
    svc = get_service(db, service_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(svc, k, v)
    db.commit()
    db.refresh(svc)
    return svc


def deactivate_service(db: Session, service_id: UUID) -> ClinicalService:
    """Soft delete: set is_active=False. Dịch vụ không còn xuất hiện khi khai khám nhưng lịch sử giữ nguyên."""
    svc = get_service(db, service_id)
    if not svc.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service is already inactive")
    svc.is_active = False
    db.commit()
    db.refresh(svc)
    return svc


def reactivate_service(db: Session, service_id: UUID) -> ClinicalService:
    svc = get_service(db, service_id)
    if svc.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service is already active")
    svc.is_active = True
    db.commit()
    db.refresh(svc)
    return svc


# ──────────────────────────────────────────
# MEDICAL RECORD (Hồ sơ bệnh án)
# ──────────────────────────────────────────

def create_record(db: Session, payload: MedicalRecordCreate) -> MedicalRecord:
    # 1. Kiểm tra Appointment
    appt = _get_or_404(db, Appointment, Appointment.appointment_id, payload.appointment_id, "Appointment")
    
    # 🛑 Validation: Phải đang khám mới được lập hồ sơ
    if appt.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create record: appointment is '{appt.status}', must be 'IN_PROGRESS'"
        )

    # 2. Không tạo 2 hồ sơ cho 1 lần khám
    existing = db.query(MedicalRecord).filter(MedicalRecord.appointment_id == payload.appointment_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Medical record already exists for this appointment")

    # 3. Tạo record chính
    record = MedicalRecord(
        appointment_id = payload.appointment_id,
        icd10_code     = payload.icd10_code,
        diagnosis      = payload.diagnosis,
        symptoms       = payload.symptoms,
        treatment_plan = payload.treatment_plan,
    )
    db.add(record)
    db.flush()

    # 4. Thêm line-item dịch vụ (Xử lý hàng loạt)
    for item in payload.services:
        price = _resolve_price(db, item)
        rs = RecordService(
            record_id    = record.record_id,
            service_id   = item.service_id,
            quantity     = item.quantity,
            actual_price = price,
        )
        db.add(rs)

    # 5. Tự động chuyển trạng thái cuộc hẹn sang COMPLETED (hoặc PENDING_PAYMENT tùy workflow)
    # appt.status = "COMPLETED" 

    db.commit()
    db.refresh(record)

    # 🚀 Thông báo cho Bệnh nhân về kết quả khám
    from app.services import notification_service
    notification_service.create_notification(db, {
        "recipient_id": appt.patient_id,
        "recipient_type": "PATIENT",
        "title": "Kết quả khám bệnh mới",
        "content": f"Hồ sơ bệnh án cho cuộc hẹn ngày {appt.appointment_date.strftime('%d/%m/%Y')} đã có kết quả. Bạn có thể xem chi tiết trong phần Lịch sử khám.",
        "notification_type": "MEDICAL_RECORD"
    })

    return get_record(db, record.record_id)


def get_record(db: Session, record_id: UUID) -> MedicalRecord:
    # Tối ưu hóa query bằng joinedload để lấy luôn thông tin dịch vụ kèm theo
    record = (
        db.query(MedicalRecord)
        .options(joinedload(MedicalRecord.services).joinedload(RecordService.service))
        .filter(MedicalRecord.record_id == record_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found")
    
    # Gán service_name cho Response Schema
    for rs in record.services:
        rs.service_name = rs.service.service_name
    return record


def get_record_by_appointment(db: Session, appointment_id: UUID) -> MedicalRecord:
    """Lấy bệnh án theo appointment_id (dùng cho endpoint /appointments/{id}/medical-record)."""
    record = (
        db.query(MedicalRecord)
        .options(joinedload(MedicalRecord.services).joinedload(RecordService.service))
        .filter(MedicalRecord.appointment_id == appointment_id)
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No medical record found for this appointment",
        )

    for rs in record.services:
        rs.service_name = rs.service.service_name
    return record


def update_record(db: Session, record_id: UUID, payload: MedicalRecordUpdate) -> MedicalRecord:
    record = get_record(db, record_id)

    # 🛑 Bảo vệ dữ liệu: Đã ký rồi thì cấm sửa (nguyên tắc y tế)
    if record.signed_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit a signed medical record"
        )

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    
    db.commit()
    db.refresh(record)
    return get_record(db, record.record_id)


def sign_record(
    db       : Session,
    record_id: UUID,
    payload  : SignRecordRequest,
    doctor_id: UUID,
) -> MedicalRecord:
    """
    Ký số hồ sơ bệnh án (Digital Signature).
    Mã hóa SHA-256 nội dung để đảm bảo tính chống chối bỏ.
    """
    record = get_record(db, record_id)

    if record.signed_at:
        raise HTTPException(status_code=400, detail="Record is already signed")

    # 🛑 Validation nghiệp vụ: Bác sĩ ký phải là người được phân công khám (nếu hệ thống yêu cầu chặt chẽ)
    # if record.appointment.doctor_id != doctor_id:
    #     raise HTTPException(403, detail="You are not authorized to sign this record")

    now = datetime.now()
    
    # Tạo chuỗi hash độc nhất
    raw_content = f"{record_id}{doctor_id}{payload.doctor_secret}{now.isoformat()}"
    signature = hashlib.sha256(raw_content.encode()).hexdigest()

    record.doctor_signature_hash = signature
    record.signed_at             = now
    
    # MaLK là mã liên kết với cổng BHYT/BHXH Việt Nam
    if payload.ma_lk:
        record.ma_lk = payload.ma_lk

    db.commit()
    db.refresh(record)
    return record


def get_records_by_patient(db: Session, patient_id: UUID) -> List[MedicalRecord]:
    """Lấy toàn bộ lịch sử khám của một bệnh nhân."""
    records = (
        db.query(MedicalRecord)
        .join(Appointment)
        .options(joinedload(MedicalRecord.services).joinedload(RecordService.service))
        .filter(Appointment.patient_id == patient_id)
        .order_by(MedicalRecord.created_at.desc())
        .all()
    )
    
    for record in records:
        for rs in record.services:
            rs.service_name = rs.service.service_name
            
    return records