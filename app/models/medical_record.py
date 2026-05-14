import uuid
from sqlalchemy import (
    Column, String, Text, Boolean,
    Integer, Numeric, ForeignKey, TIMESTAMP, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class MedicalRecord(Base):
    __tablename__ = "medical_record"

    record_id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id        = Column(UUID(as_uuid=True), ForeignKey("appointment.appointment_id", ondelete="RESTRICT"), nullable=False, unique=True)
    ma_lk                 = Column(String(50), unique=True, nullable=True)   # Mã liên kết cổng BHYT
    icd10_code            = Column(String(10), nullable=True)                # VD: J06.9
    diagnosis             = Column(Text, nullable=False)                     # Nên mã hoá AES ở backend
    symptoms              = Column(Text, nullable=True)
    treatment_plan        = Column(Text, nullable=True)
    doctor_signature_hash = Column(Text, nullable=True)                      # Chữ ký số SHA-256
    signed_at             = Column(TIMESTAMP, nullable=True)
    created_at            = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    appointment   = relationship("Appointment",    back_populates="medical_records")
    services      = relationship("RecordService",  back_populates="record", lazy="select", cascade="all, delete-orphan")
    prescriptions = relationship("Prescription",   back_populates="record", lazy="select")

    __table_args__ = (
        Index("idx_record_appointment", "appointment_id"),
    )


class ClinicalService(Base):
    __tablename__ = "clinical_service"

    service_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_code    = Column(String(50), unique=True, nullable=False)
    service_name    = Column(String(255), nullable=False)
    price           = Column(Numeric(10, 2), nullable=False)
    is_bhyt_covered = Column(Boolean, default=True)
    is_active       = Column(Boolean, default=True)

    # Relationships
    record_services = relationship("RecordService", back_populates="service", lazy="select")


class RecordService(Base):
    __tablename__ = "record_service"

    record_service_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id         = Column(UUID(as_uuid=True), ForeignKey("medical_record.record_id",  ondelete="RESTRICT"), nullable=False)
    service_id        = Column(UUID(as_uuid=True), ForeignKey("clinical_service.service_id", ondelete="RESTRICT"), nullable=False)
    quantity          = Column(Integer, default=1)
    actual_price      = Column(Numeric(10, 2), nullable=False)  # Giá snapshot tại thời điểm chỉ định
    created_at        = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    record  = relationship("MedicalRecord",   back_populates="services")
    service = relationship("ClinicalService", back_populates="record_services")