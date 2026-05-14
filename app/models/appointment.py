import uuid
from sqlalchemy import (
    Column, String, ForeignKey, TIMESTAMP,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class Appointment(Base):
    __tablename__ = "appointment"

    appointment_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id      = Column(UUID(as_uuid=True), ForeignKey("patient.patient_id",       ondelete="RESTRICT"), nullable=False)
    doctor_id       = Column(UUID(as_uuid=True), ForeignKey("doctor.doctor_id",         ondelete="RESTRICT"), nullable=False)
    schedule_id     = Column(UUID(as_uuid=True), ForeignKey("doctor_schedule.schedule_id", ondelete="RESTRICT"), nullable=False)
    applied_bhyt_id = Column(UUID(as_uuid=True), ForeignKey("patient_bhyt.bhyt_id",     ondelete="RESTRICT"), nullable=True)
    appointment_date= Column(TIMESTAMP, nullable=False)
    
    # Cập nhật: Thêm trạng thái PENDING_PAYMENT làm mặc định khi vừa book xong
    status          = Column(String(50), default="PENDING_PAYMENT") # PENDING_PAYMENT | SCHEDULED | CHECKED_IN | IN_PROGRESS | COMPLETED | CANCELLED | NO_SHOW
    
    # Bổ sung: Lưu thời gian hết hạn giữ chỗ (ví dụ: created_at + 10 phút)
    locked_until    = Column(TIMESTAMP, nullable=True) 
    
    created_at      = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    patient      = relationship("Patient",      back_populates="appointments")
    doctor       = relationship("Doctor",       back_populates="appointments")
    schedule     = relationship("DoctorSchedule", back_populates="appointments")
    applied_bhyt = relationship("PatientBHYT",  back_populates="appointments")
    medical_records = relationship("MedicalRecord", back_populates="appointment", lazy="select")
    billing         = relationship("Billing",       back_populates="appointment", uselist=False, lazy="select")

    __table_args__ = (
        # Chống spam: 1 bệnh nhân không đặt 2 lần cùng 1 slot
        UniqueConstraint("patient_id", "schedule_id", name="uq_patient_schedule"),
        Index("idx_appointment_status", "status", "appointment_date"),
        Index("idx_appointment_patient", "patient_id"),
        Index("idx_appointment_doctor",  "doctor_id"),
    )