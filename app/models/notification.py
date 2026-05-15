import uuid
from sqlalchemy import Column, String, Text, Integer, ForeignKey, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class Notification(Base):
    __tablename__ = "notification"

    notification_id   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id      = Column(UUID(as_uuid=True), nullable=False)
    recipient_type    = Column(String(20), nullable=False)    # PATIENT | DOCTOR
    notification_type = Column(String(50), nullable=False)    # BHYT_EXPIRATION | APPOINTMENT_REMINDER | BILLING_SUCCESS | HR_SUPPORT
    channel           = Column(String(20), default="EMAIL")   # EMAIL | SMS | PUSH
    title             = Column(String(255))
    content           = Column(Text)
    status            = Column(String(20), default="PENDING") # PENDING | SENT | FAILED
    retry_count       = Column(Integer, default=0)
    sent_at           = Column(TIMESTAMP)
    created_at        = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (Index("idx_notif_status", "status", "created_at"),)


class SupportRequest(Base):
    __tablename__ = "support_request"

    request_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id  = Column(UUID(as_uuid=True), ForeignKey("patient.patient_id", ondelete="RESTRICT"), nullable=False)
    request_type= Column(String(50), nullable=False)
    title       = Column(String(255))
    content     = Column(Text)
    assigned_to = Column(UUID(as_uuid=True), nullable=True)   # doctor_id or staff UUID
    priority    = Column(String(10), default="NORMAL")        # LOW|NORMAL|HIGH|URGENT
    status      = Column(String(20), default="OPEN")          # OPEN|IN_PROGRESS|RESOLVED|CLOSED
    resolved_at = Column(TIMESTAMP)
    created_at  = Column(TIMESTAMP, server_default=func.now())

    patient = relationship("Patient", lazy="select")