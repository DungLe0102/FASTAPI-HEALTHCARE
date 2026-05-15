from uuid import UUID
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# ── Notification Schemas ──────────────────────────

class NotificationCreate(BaseModel):
    recipient_id      : UUID
    recipient_type    : Literal["PATIENT", "DOCTOR"] = "PATIENT"
    notification_type : str # nới lỏng để hỗ trợ nhiều loại thông báo hơn
    channel           : Literal["EMAIL", "SMS", "PUSH"] = "EMAIL"
    title             : Optional[str] = None
    content           : Optional[str] = None

class NotificationResponse(NotificationCreate):
    notification_id : UUID
    status          : str
    retry_count     : int
    sent_at         : Optional[datetime]
    created_at      : datetime
    model_config = ConfigDict(from_attributes=True)


# ── Support Request Schemas ───────────────────────

class SupportRequestCreate(BaseModel):
    patient_id   : UUID
    request_type : str  = Field(..., max_length=50)
    title        : str  = Field(..., max_length=255)
    content      : Optional[str] = None
    priority     : Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"

class SupportRequestUpdate(BaseModel):
    assigned_to : Optional[UUID]   = None
    priority    : Optional[Literal["LOW", "NORMAL", "HIGH", "URGENT"]] = None
    status      : Optional[Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]] = None

class SupportRequestResponse(BaseModel):
    request_id  : UUID
    patient_id  : UUID
    request_type: str
    title       : str
    content     : Optional[str]
    assigned_to : Optional[UUID]
    priority    : str
    status      : str
    resolved_at : Optional[datetime]
    created_at  : datetime
    model_config = {"from_attributes": True}