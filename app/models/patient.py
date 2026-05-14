import uuid
from sqlalchemy import (
    Column, String, Boolean, Date, Text,
    ForeignKey, TIMESTAMP, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class Patient(Base):
    __tablename__ = "patient"

    patient_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name  = Column(String(100), nullable=False)
    last_name   = Column(String(100), nullable=False)
    dob         = Column(Date, nullable=False)
    gender      = Column(String(10))
    phone       = Column(String(20), unique=True)
    cccd        = Column(String(12), unique=True)
    address     = Column(Text)
    created_at  = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    bhyt_records = relationship("PatientBHYT",    back_populates="patient", lazy="select")
    consents     = relationship("PatientConsent", back_populates="patient", lazy="select")
    appointments = relationship("Appointment",    back_populates="patient", lazy="select")


class PatientBHYT(Base):
    __tablename__ = "patient_bhyt"

    bhyt_id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id               = Column(UUID(as_uuid=True), ForeignKey("patient.patient_id", ondelete="RESTRICT"), nullable=False)
    bhyt_code                = Column(String(15), unique=True, nullable=False)
    registered_hospital_code = Column(String(20))
    valid_from               = Column(Date, nullable=False)
    valid_to                 = Column(Date, nullable=False)
    is_active                = Column(Boolean, default=True)
    check_status             = Column(String(50), default="PENDING")   # PENDING | VERIFIED | FAILED
    
    # Bổ sung: Lưu lại ngày cuối cùng được gia hạn tự động qua VietQR để đối soát
    last_extension_date      = Column(Date, nullable=True) 
    
    created_at               = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    patient      = relationship("Patient",      back_populates="bhyt_records")
    appointments = relationship("Appointment",  back_populates="applied_bhyt", lazy="select")

    __table_args__ = (
        Index("idx_patient_bhyt_code", "bhyt_code"),
    )


class PatientConsent(Base):
    __tablename__ = "patient_consent"

    consent_id   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id   = Column(UUID(as_uuid=True), ForeignKey("patient.patient_id", ondelete="RESTRICT"), nullable=False)
    consent_type = Column(String(50), nullable=False)   # e.g. DATA_PROCESSING, MARKETING
    is_granted   = Column(Boolean, nullable=False, default=False)
    ip_address   = Column(String(45))
    user_agent   = Column(Text)
    timestamp    = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    patient = relationship("Patient", back_populates="consents")

    __table_args__ = (
        Index("idx_patient_consent", "patient_id", "is_granted"),
    )