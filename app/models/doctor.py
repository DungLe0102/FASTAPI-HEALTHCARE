import uuid
from sqlalchemy import (
    Column, String, Boolean, Integer,
    ForeignKey, TIMESTAMP, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class Doctor(Base):
    __tablename__ = "doctor"

    doctor_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id  = Column(UUID(as_uuid=True), ForeignKey("department.department_id", ondelete="SET NULL"), nullable=True)
    first_name     = Column(String(100), nullable=False)
    last_name      = Column(String(100), nullable=False)
    specialization = Column(String(100), nullable=False)
    is_active      = Column(Boolean, default=True)
    is_simulator   = Column(Boolean, default=False)   # flag bác sĩ test/demo
    
    # Bổ sung: Phí tư vấn theo giờ (VND) để tạo hóa đơn thanh toán VietQR
    hourly_consultation_fee = Column(Integer, default=0, nullable=False)

    # Relationships
    department  = relationship("Department",    back_populates="doctors")
    schedules   = relationship("DoctorSchedule", back_populates="doctor", lazy="select")
    appointments = relationship("Appointment",  back_populates="doctor",  lazy="select")
    prescriptions = relationship("Prescription", back_populates="doctor", lazy="select")


class DoctorSchedule(Base):
    __tablename__ = "doctor_schedule"

    schedule_id    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id      = Column(UUID(as_uuid=True), ForeignKey("doctor.doctor_id",  ondelete="RESTRICT"), nullable=False)
    room_id        = Column(UUID(as_uuid=True), ForeignKey("room.room_id",      ondelete="RESTRICT"), nullable=False)
    start_time     = Column(TIMESTAMP, nullable=False)
    end_time       = Column(TIMESTAMP, nullable=False)
    max_patients   = Column(Integer, default=1)
    current_booked = Column(Integer, default=0)
    status         = Column(String(20), default="AVAILABLE")  # AVAILABLE | FULL | CANCELLED

    # Relationships
    doctor       = relationship("Doctor", back_populates="schedules")
    room         = relationship("Room",   back_populates="schedules")
    appointments = relationship("Appointment", back_populates="schedule", lazy="select")

    __table_args__ = (
        # Chống double-book: 1 bác sĩ không có 2 ca cùng start_time
        UniqueConstraint("doctor_id", "start_time", name="uq_doctor_schedule"),
        Index("idx_doc_schedule_time", "doctor_id", "start_time", "status"),
    )