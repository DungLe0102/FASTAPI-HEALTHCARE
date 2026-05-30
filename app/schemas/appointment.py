from uuid import UUID
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────
# STATUS MACHINE
# ─────────────────────────────────────────────
#
#   SCHEDULED → CHECKED_IN → IN_PROGRESS → COMPLETED
#       ↓            ↓            ↓
#   CANCELLED    CANCELLED    CANCELLED
#       ↓
#   NO_SHOW  (chỉ từ SCHEDULED khi qua giờ hẹn)
#
VALID_TRANSITIONS: dict[str, list[str]] = {
    "PENDING_PAYMENT": ["SCHEDULED", "CANCELLED"],
    "SCHEDULED"  : ["CHECKED_IN", "CANCELLED", "NO_SHOW"],
    "CHECKED_IN" : ["IN_PROGRESS", "CANCELLED"],
    "IN_PROGRESS": ["COMPLETED",  "CANCELLED"],
    "COMPLETED"  : [],        # terminal
    "CANCELLED"  : [],        # terminal
    "NO_SHOW"    : [],        # terminal
}

ALL_STATUSES = list(VALID_TRANSITIONS.keys())


# ─────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────

class AppointmentCreate(BaseModel):
    patient_id      : UUID = Field(..., examples=["c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39"])
    schedule_id     : UUID = Field(..., examples=["d2e6f2d1-9ebc-5fb9-a5d0-12e44efec740"])
    applied_bhyt_id : Optional[UUID] = Field(None, examples=["e3f7g3e2-0fcd-6ge0-b6e1-23f55fgfd851"])

    model_config = {
        "json_schema_extra": {
            "example": {
                "patient_id": "c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39",
                "schedule_id": "d2e6f2d1-9ebc-5fb9-a5d0-12e44efec740",
                "applied_bhyt_id": "e3f7g3e2-0fcd-6ge0-b6e1-23f55fgfd851"
            }
        }
    }


class AppointmentStatusUpdate(BaseModel):
    """Chỉ cho phép thay đổi status theo state machine."""
    status: str = Field(..., examples=["CHECKED_IN"])

    @model_validator(mode="after")
    def validate_status(self):
        if self.status not in ALL_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {ALL_STATUSES}")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "CHECKED_IN"
            }
        }
    }


# ─────────────────────────────────────────────
# RESPONSE SCHEMAS
# ─────────────────────────────────────────────

class AppointmentResponse(BaseModel):
    appointment_id  : UUID
    patient_id      : UUID
    doctor_id       : UUID
    schedule_id     : UUID
    applied_bhyt_id : Optional[UUID]
    appointment_date: datetime
    status          : str
    created_at      : datetime

    # Tích hợp hóa đơn và mã QR trả về ngay khi book lịch
    billing_id      : Optional[UUID] = None
    payment_qr_url  : Optional[str] = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "appointment_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6",
                "patient_id": "c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39",
                "doctor_id": "d1e2f3g4-h5i6-j7k8-l9m0-n1o2p3q4r5s6",
                "schedule_id": "d2e6f2d1-9ebc-5fb9-a5d0-12e44efec740",
                "applied_bhyt_id": None,
                "appointment_date": "2026-06-01T08:00:00Z",
                "status": "PENDING_PAYMENT",
                "created_at": "2026-05-08T14:00:00Z",
                "billing_id": "b1c2d3e4-f5g6-h7i8-j9k0-l1m2n3o4p5q6",
                "payment_qr_url": "https://api.vietqr.io/image/970403-12345678-abc.jpg"
            }
        }
    }


class AppointmentDetailResponse(AppointmentResponse):
    """Full response with nested doctor + patient info."""
    doctor_name     : Optional[str] = None
    patient_name    : Optional[str] = None
    specialization  : Optional[str] = None
    bhyt_code       : Optional[str] = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "appointment_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6",
                "patient_id": "c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39",
                "doctor_name": "Nguyen Van B",
                "patient_name": "Tran Thi C",
                "specialization": "Nội tổng quát",
                "status": "SCHEDULED",
                "appointment_date": "2026-06-01T08:00:00Z"
            }
        }
    }


class AppointmentListResponse(BaseModel):
    total       : int
    appointments: List[AppointmentDetailResponse]