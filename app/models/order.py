import uuid
from sqlalchemy import Column, String, ForeignKey, TIMESTAMP, Numeric, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base

class Order(Base):
    __tablename__ = "orders"

    order_id     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id   = Column(UUID(as_uuid=True), ForeignKey("patient.patient_id", ondelete="RESTRICT"), nullable=False)
    order_type   = Column(String(50), nullable=False) # BHYT_EXTENSION | PHARMACY
    total_amount = Column(Numeric(12, 2), nullable=False)
    status       = Column(String(50), default="PENDING") # PENDING | PAID | CANCELLED
    created_at   = Column(TIMESTAMP, server_default=func.now())
    expires_at   = Column(TIMESTAMP, nullable=False)
    
    # Store specific data like extension_months or medication list
    order_metadata = Column(JSON)

    patient = relationship("Patient")

    __table_args__ = (
        Index("idx_order_status_expires", "status", "expires_at"),
    )
