import uuid
from sqlalchemy import (
    Column, String, Boolean, Integer, Text,
    ForeignKey, TIMESTAMP, Date, Numeric, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class Medication(Base):
    __tablename__ = "medication"

    medication_id     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    med_code          = Column(String(50),  unique=True, nullable=False)
    med_name          = Column(String(255), nullable=False)
    active_ingredient = Column(String(255))
    unit              = Column(String(20),  nullable=False)
    price             = Column(Numeric(10, 2), nullable=False)
    is_bhyt_covered   = Column(Boolean, default=True)
    is_active         = Column(Boolean, default=True)

    inventory_batches  = relationship("Inventory",         back_populates="medication", lazy="select")
    prescription_items = relationship("PrescriptionItem",  back_populates="medication", lazy="select")


class Inventory(Base):
    __tablename__ = "inventory"

    inventory_id    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medication_id   = Column(UUID(as_uuid=True), ForeignKey("medication.medication_id", ondelete="RESTRICT"), nullable=False)
    batch_number    = Column(String(50), nullable=False)
    quantity        = Column(Integer, default=0, nullable=False)
    expiration_date = Column(Date, nullable=False)
    updated_at      = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    medication = relationship("Medication", back_populates="inventory_batches")

    from sqlalchemy import CheckConstraint
    __table_args__ = (
        Index("idx_inventory_med", "medication_id", "expiration_date"),
        CheckConstraint("quantity >= 0", name="chk_inventory_qty_positive"),
    )


class Prescription(Base):
    __tablename__ = "prescription"

    prescription_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id             = Column(UUID(as_uuid=True), ForeignKey("medical_record.record_id", ondelete="RESTRICT"), nullable=False)
    doctor_id             = Column(UUID(as_uuid=True), ForeignKey("doctor.doctor_id",         ondelete="RESTRICT"), nullable=False)
    notes                 = Column(Text)
    doctor_signature_hash = Column(Text)
    signed_at             = Column(TIMESTAMP)
    created_at            = Column(TIMESTAMP, server_default=func.now())

    record = relationship("MedicalRecord",   back_populates="prescriptions")
    doctor = relationship("Doctor",          back_populates="prescriptions")
    items  = relationship("PrescriptionItem", back_populates="prescription", lazy="select")

    __table_args__ = (
        Index("idx_prescription_record", "record_id"),
    )


class PrescriptionItem(Base):
    __tablename__ = "prescription_item"

    item_id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prescription_id    = Column(UUID(as_uuid=True), ForeignKey("prescription.prescription_id", ondelete="RESTRICT"), nullable=False)
    medication_id      = Column(UUID(as_uuid=True), ForeignKey("medication.medication_id",     ondelete="RESTRICT"), nullable=False)
    quantity           = Column(Integer, nullable=False)
    dosage_instruction = Column(Text)

    prescription = relationship("Prescription",  back_populates="items")
    medication   = relationship("Medication",    back_populates="prescription_items")

    __table_args__ = (
        Index("idx_prescription_item_prescription", "prescription_id"),
    )