import uuid
from sqlalchemy import Column, String, Boolean, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db import Base


class Account(Base):
    __tablename__ = "account"

    account_id    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email         = Column(String(255), unique=True, nullable=False, index=True)   # template uses email
    full_name     = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role          = Column(String(20), nullable=False)   # ADMIN | PATIENT
    is_active      = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)          # True sau khi xác minh OTP
    otp_code       = Column(String(6), nullable=True)         # OTP 6 số
    otp_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    otp_purpose    = Column(String(20), nullable=True)        # VERIFY_EMAIL | RESET_PASSWORD
    last_login     = Column(TIMESTAMP)
    created_at     = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (Index("idx_account_email", "email"),)