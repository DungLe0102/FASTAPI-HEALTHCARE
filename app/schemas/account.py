from uuid import UUID
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field


# ── Roles (giữ nguyên từ code gốc) ───────────────────────────────────────────
ROLES = Literal["ADMIN", "PATIENT"]


# ── Signup (ai cũng có thể tự đăng ký — template UserRegister) ───────────────

class UserRegister(BaseModel):
    """Bệnh nhân tự đăng ký. Chỉ cần Email và Password."""
    email: EmailStr = Field(..., max_length=255, examples=["nguyenvana@gmail.com"])
    password: str = Field(..., min_length=8, max_length=128, examples=["Password123!"])


# ── ADMIN tạo account có role cụ thể ─────────────────────────────────────────

class AccountCreate(BaseModel):
    """ADMIN tạo tài khoản, gán role."""
    email: EmailStr = Field(..., max_length=255, examples=["admin@healthcare.local"])
    password: str = Field(..., min_length=8, max_length=128, description="Minimum 8 characters", examples=["changethis"])
    full_name: str | None = Field(default=None, max_length=255, examples=["System Administrator"])
    role: ROLES = "PATIENT"


# ── Update (ADMIN cập nhật account) ──────────────────────────────────────────

class AccountUpdate(BaseModel):
    email: Optional[EmailStr] = Field(default=None, max_length=255, examples=["updated@example.com"])
    full_name: Optional[str] = Field(default=None, max_length=255, examples=["New Name"])
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    role: Optional[ROLES] = None
    is_active: Optional[bool] = None


# ── Update me (user tự cập nhật) ─────────────────────────────────────────────

class UpdateMe(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255, examples=["Van A Nguyen"])
    email: Optional[EmailStr] = Field(default=None, max_length=255, examples=["newemail@gmail.com"])


# ── Response ──────────────────────────────────────────────────────────────────

class AccountResponse(BaseModel):
    account_id: UUID
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    email_verified: bool
    last_login: Optional[datetime]
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "account_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6",
                "email": "user@example.com",
                "full_name": "Nguyen Van A",
                "role": "PATIENT",
                "is_active": True,
                "email_verified": True,
                "created_at": "2026-05-08T14:00:00Z"
            }
        }
    }


# ── Token — template Token schema ─────────────────────────────────────────────

class Token(BaseModel):
    """Trả về từ /login — bổ sung role & account_id để frontend dùng ngay."""
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    role: Optional[str] = None          # ADMIN | PATIENT
    account_id: Optional[str] = None    # UUID dạng string

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI...",
                "role": "ADMIN",
                "account_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6"
            }
        }
    }


class RefreshRequest(BaseModel):
    refresh_token: str


# Giữ alias cũ để không cần sửa các router khác
TokenResponse = Token


# ── Password change ───────────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="Minimum 8 characters")


# ── Password recovery (template NewPassword) ──────────────────────────────────

class NewPassword(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


# ── Generic message ───────────────────────────────────────────────────────────

class Message(BaseModel):
    message: str

# ── OTP — forgot password ──────────────────────────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., examples=["nguyenvana@gmail.com"])


class VerifyResetOTPRequest(BaseModel):
    email: EmailStr = Field(..., examples=["nguyenvana@gmail.com"])
    otp: str = Field(..., min_length=6, max_length=6, examples=["123456"])


class VerifyResetOTPResponse(BaseModel):
    reset_token: str
    message: str


class ResendOTPRequest(BaseModel):
    email: EmailStr = Field(..., examples=["nguyenvana@gmail.com"])