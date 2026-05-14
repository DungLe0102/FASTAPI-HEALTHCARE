import uuid
from sqlalchemy import Column, String, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id         = Column(UUID(as_uuid=True), nullable=False)
    actor_role       = Column(String(20),  nullable=False)
    action_type      = Column(String(20),  nullable=False)   # CREATE|UPDATE|DELETE|READ
    target_table     = Column(String(50),  nullable=False)
    target_record_id = Column(UUID(as_uuid=True), nullable=False)
    ip_address       = Column(String(45))
    timestamp        = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_audit_target", "target_table", "target_record_id"),
        Index("idx_audit_actor",  "actor_id", "timestamp"),
    )