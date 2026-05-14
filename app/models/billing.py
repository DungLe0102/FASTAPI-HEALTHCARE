import uuid
from sqlalchemy import Column, String, ForeignKey, TIMESTAMP, Numeric, Index, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class Billing(Base):
    __tablename__ = "billing"

    billing_id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id      = Column(UUID(as_uuid=True), ForeignKey("appointment.appointment_id", ondelete="RESTRICT"), nullable=False)
    total_amount        = Column(Numeric(12, 2), nullable=False)
    bhyt_covered_amount = Column(Numeric(12, 2), default=0)
    patient_paid_amount = Column(Numeric(12, 2), nullable=False)
    billing_status      = Column(String(50), default="UNPAID")   # UNPAID|PARTIAL|PAID|REFUNDED
    created_at          = Column(TIMESTAMP, server_default=func.now())

    appointment  = relationship("Appointment",        back_populates="billing")
    transactions = relationship("PaymentTransaction", back_populates="billing", lazy="select")

    __table_args__ = (Index("idx_billing_appointment", "appointment_id"),)


class PaymentTransaction(Base):
    __tablename__ = "payment_transaction"

    transaction_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    billing_id           = Column(UUID(as_uuid=True), ForeignKey("billing.billing_id", ondelete="RESTRICT"), nullable=False)
    payment_method       = Column(String(50), default="VIETQR")    # CASH|VIETQR|BANK_TRANSFER
    amount               = Column(Numeric(12, 2), nullable=False)
    gateway_reference_id = Column(String(255))
    transaction_status   = Column(String(50), default="PENDING")   # PENDING|SUCCESS|FAILED
    payment_date         = Column(TIMESTAMP)

    billing = relationship("Billing", back_populates="transactions")

    __table_args__ = (
        Index("idx_payment_transaction_billing", "billing_id", "transaction_status"),
    )


class DoctorPayout(Base):
    __tablename__ = "doctor_payout"

    payout_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id      = Column(UUID(as_uuid=True), ForeignKey("doctor.doctor_id", ondelete="RESTRICT"), nullable=False)
    amount         = Column(Numeric(12, 2), nullable=False)
    payout_date    = Column(Date, nullable=False)
    status         = Column(String(50), default="PENDING")   # PENDING|PAID|CANCELLED
    period_start   = Column(Date, nullable=False)
    period_end     = Column(Date, nullable=False)
    notes          = Column(String(255))
    created_at     = Column(TIMESTAMP, server_default=func.now())

    doctor = relationship("Doctor", backref="payouts")

    __table_args__ = (
        Index("idx_doctor_payout_doc_status", "doctor_id", "status"),
    )