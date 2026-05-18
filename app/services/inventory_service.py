from uuid import UUID
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.inventory import Medication, Inventory, Prescription, PrescriptionItem
from app.models.medical_record import MedicalRecord
from app.models.doctor import Doctor
from app.schemas.inventory import (
    MedicationCreate, MedicationUpdate,
    InventoryCreate, InventoryAdjust,
    PrescriptionCreate, PrescriptionSign,
)

# ── HELPERS ───────────────────────────────────────

def _404(db: Session, model, col, val, label: str):
    obj = db.query(model).filter(col == val).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"{label} '{val}' not found"
        )
    return obj

# ── Medication ────────────────────────────────────

def list_medications(db: Session, active_only: bool = False) -> List[Medication]:
    q = db.query(Medication)
    if active_only:
        q = q.filter(Medication.is_active == True)
    return q.order_by(Medication.med_code).all()

def get_medication(db: Session, medication_id: UUID) -> Medication:
    return _404(db, Medication, Medication.medication_id, medication_id, "Medication")

def create_medication(db: Session, payload: MedicationCreate) -> Medication:
    med = Medication(**payload.model_dump())
    db.add(med)
    try:
        db.commit()
        db.refresh(med)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail=f"Medication code '{payload.med_code}' already exists"
        )
    return med

def update_medication(db: Session, medication_id: UUID, payload: MedicationUpdate) -> Medication:
    med = get_medication(db, medication_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(med, k, v)
    db.commit()
    db.refresh(med)
    return med

def deactivate_medication(db: Session, medication_id: UUID) -> Medication:
    """Soft delete: set is_active=False. Không xóa dữ liệu để giữ lịch sử kê đơn."""
    med = get_medication(db, medication_id)
    if not med.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Medication is already inactive")
    med.is_active = False
    db.commit()
    db.refresh(med)
    return med

def reactivate_medication(db: Session, medication_id: UUID) -> Medication:
    med = get_medication(db, medication_id)
    if med.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Medication is already active")
    med.is_active = True
    db.commit()
    db.refresh(med)
    return med

# ── Inventory (Kho thuốc) ──────────────────────────

def list_inventory(db: Session, medication_id: Optional[UUID] = None) -> List[Inventory]:
    q = db.query(Inventory)
    if medication_id:
        q = q.filter(Inventory.medication_id == medication_id)
    return q.order_by(Inventory.expiration_date).all()

def get_stock_total(db: Session, medication_id: UUID) -> int:
    today = date.today()
    rows = db.query(Inventory).join(Medication).filter(
        Inventory.medication_id == medication_id,
        Inventory.expiration_date >= today,
        Medication.is_active == True
    ).all()
    return sum(r.quantity for r in rows)

def add_inventory_batch(db: Session, payload: InventoryCreate) -> Inventory:
    med = get_medication(db, payload.medication_id)
    if not med.is_active:
        raise HTTPException(status_code=400, detail="Cannot add stock to an inactive medication")

    if payload.expiration_date < date.today():
        raise HTTPException(status_code=400, detail="Cannot add an expired batch to inventory")

    batch = Inventory(**payload.model_dump())
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch

def adjust_inventory(db: Session, inventory_id: UUID, payload: InventoryAdjust) -> Inventory:
    inv = db.query(Inventory).filter(Inventory.inventory_id == inventory_id).with_for_update().first()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Inventory '{inventory_id}' not found")
    
    new_qty = inv.quantity + payload.delta
    if new_qty < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Insufficient stock. Current: {inv.quantity}, reduction: {abs(payload.delta)}"
        )
    
    inv.quantity = new_qty
    db.commit()
    db.refresh(inv)
    return inv

def get_expiring_soon(db: Session, days: int = 30) -> List[Inventory]:
    cutoff = date.today() + timedelta(days=days)
    return db.query(Inventory).filter(
        Inventory.expiration_date <= cutoff,
        Inventory.expiration_date >= date.today(),
        Inventory.quantity > 0,
    ).order_by(Inventory.expiration_date).all()

# ── Prescription (Đơn thuốc) ───────────────────────

def get_prescription(db: Session, prescription_id: UUID) -> Prescription:
    """Hàm bổ sung để sửa lỗi undefined"""
    return _404(db, Prescription, Prescription.prescription_id, prescription_id, "Prescription")

def _deduct_stock(db: Session, medication_id: UUID, qty_needed: int) -> list:
    """
    Kiểm tra và trừ số lượng thuốc tồn kho theo nguyên tắc FIFO (nhập trước xuất trước).
    Nếu không đủ thuốc -> trả lỗi ngay.
    Trả về danh sách các batch và số lượng đã trừ để có thể hoàn lại chính xác.
    """
    if qty_needed <= 0:
        return [] # Không cần trừ nếu số lượng là 0
    today = date.today()
    med = db.query(Medication).filter(Medication.medication_id == medication_id).first()
    #SELECT * FROM inventory JOIN medication ON inventory.medication_id = medication.medication_id WHERE medication.is_active = true;
    if not med or not med.is_active:
        raise HTTPException(status_code=400, detail=f"Medication {medication_id} is inactive or not found")

    batches = db.query(Inventory).filter(
        Inventory.medication_id   == medication_id,
        Inventory.expiration_date >= today,
        Inventory.quantity        > 0,
    ).order_by(Inventory.expiration_date).with_for_update().all()
    #

    total_available = sum(b.quantity for b in batches)
    if total_available < qty_needed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock for '{med.med_name}'. Available: {total_available}, needed: {qty_needed}",
        )

    remaining = qty_needed
    deducted_batches = []
    for batch in batches:
        if qty_needed == 0:
            break
        
        deduct = min(batch.quantity, qty_needed)
        batch.quantity -= deduct
        qty_needed -= deduct
        deducted_batches.append({"inventory_id": str(batch.inventory_id), "quantity": deduct})
        
    return deducted_batches


def _restore_stock(db: Session, medication_id: UUID, qty_to_restore: int, deducted_batches: list = None):
    """
    Trọng tài: Hoàn trả số lượng thuốc về kho (dùng cho Inventory Reservation).
    Sử dụng deducted_batches để cộng lại đúng lô bị trừ (đảm bảo đúng FIFO hạn sử dụng).
    Nếu không có (đơn cũ), dùng lô có hạn xa nhất làm fallback.
    """
    if qty_to_restore <= 0:
        return
        
    if deducted_batches:
        for b_info in deducted_batches:
            inv_id = UUID(b_info["inventory_id"])
            qty = b_info["quantity"]
            batch = db.query(Inventory).filter(Inventory.inventory_id == inv_id).with_for_update().first()
            if batch:
                batch.quantity += qty
        return

    today = date.today()
    # Fallback cho đơn hàng cũ: Tìm lô hàng còn hạn ưu tiên lô gần hết hạn để cộng vào (hoặc lô mới nhất tùy chiến lược)
    # Ở đây ta ưu tiên lô còn hiệu lực có ngày hết hạn xa nhất để tránh thuốc bị vứt bỏ.
    batch = db.query(Inventory).filter(
        Inventory.medication_id == medication_id,
        Inventory.expiration_date >= today
    ).order_by(Inventory.expiration_date.desc()).with_for_update().first()
    
    if batch:
        batch.quantity += qty_to_restore
    else:
        # Nếu không còn lô nào (rất hiếm), tạo tạm lô fallback hoặc log lỗi.
        # Tạm thời throw 500 hoặc bỏ qua.
        pass

def create_prescription(db: Session, payload: PrescriptionCreate) -> Prescription:
    if not payload.items:
        raise HTTPException(status_code=400, detail="Prescription must have at least one medication item")

    # Validate record + doctor exist (avoid FK 500)
    record = _404(db, MedicalRecord, MedicalRecord.record_id, payload.record_id, "MedicalRecord")
    doctor = _404(db, Doctor, Doctor.doctor_id, payload.doctor_id, "Doctor")
    if not doctor.is_active:
        raise HTTPException(status_code=400, detail="Doctor is inactive")

    # Guard: one prescription per medical record (avoid duplicate)
    existing = db.query(Prescription).filter(Prescription.record_id == payload.record_id).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Prescription already exists for this medical record")

    rx = Prescription(
        record_id = payload.record_id,
        doctor_id = payload.doctor_id,
        notes     = payload.notes,
    )
    db.add(rx)
    db.flush() 

    # Sort items by medication_id to prevent database deadlocks when locking inventory rows concurrently
    sorted_items = sorted(payload.items, key=lambda x: str(x.medication_id))
    for item in sorted_items:
        _deduct_stock(db, item.medication_id, item.quantity)
        
        db.add(PrescriptionItem(
            prescription_id    = rx.prescription_id,
            medication_id      = item.medication_id,
            quantity           = item.quantity,
            dosage_instruction = item.dosage_instruction,
        ))

    try:
        db.commit()
        db.refresh(rx)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create prescription: {str(e)}")
        
    return rx

def sign_prescription(db: Session, prescription_id: UUID, payload: PrescriptionSign) -> Prescription:
    # Gọi hàm get_prescription đã được định nghĩa ở trên
    rx = get_prescription(db, prescription_id)
    
    if rx.signed_at:
        raise HTTPException(status_code=400, detail="Prescription already signed")
    
    if not payload.doctor_signature_hash:
        raise HTTPException(status_code=400, detail="Digital signature hash is required")

    rx.doctor_signature_hash = payload.doctor_signature_hash
    rx.signed_at             = datetime.now()
    
    db.commit()
    db.refresh(rx)

    # 🚀 Thông báo cho Bệnh nhân về đơn thuốc mới
    from app.services import notification_service
    from app.models.appointment import Appointment
    # Truy vết ngược từ MedicalRecord để lấy patient_id
    appt = db.query(Appointment).filter(Appointment.appointment_id == rx.record.appointment_id).first()
    if appt:
        notification_service.create_notification(db, {
            "recipient_id": appt.patient_id,
            "recipient_type": "PATIENT",
            "title": "Đơn thuốc mới đã được ký",
            "content": f"Đơn thuốc cho cuộc hẹn ngày {appt.appointment_date.strftime('%d/%m/%Y')} đã được bác sĩ ký duyệt. Bạn có thể lấy thuốc tại quầy thuốc.",
            "notification_type": "PRESCRIPTION"
        })

    return rx