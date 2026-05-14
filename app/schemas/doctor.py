from uuid import UUID
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────
# DOCTOR SCHEMAS
# ──────────────────────────────────────────

class DoctorBase(BaseModel):
    first_name     : str           = Field(..., max_length=100, examples=["Tran"])
    last_name      : str           = Field(..., max_length=100, examples=["Van B"])
    specialization : str           = Field(..., max_length=100, examples=["Cardiology"])
    department_id  : Optional[UUID] = None
    is_active      : bool           = True
    is_simulator   : bool           = False


class DoctorCreate(DoctorBase):
    pass


class DoctorUpdate(BaseModel):
    first_name     : Optional[str]  = Field(None, max_length=100)
    last_name      : Optional[str]  = Field(None, max_length=100)
    specialization : Optional[str]  = Field(None, max_length=100)
    department_id  : Optional[UUID] = None
    is_active      : Optional[bool] = None


class DoctorResponse(DoctorBase):
    doctor_id: UUID

    model_config = {"from_attributes": True}


class DoctorWithSchedules(DoctorResponse):
    schedules: List["ScheduleResponse"] = []


# ──────────────────────────────────────────
# SCHEDULE SCHEMAS
# ──────────────────────────────────────────

SCHEDULE_STATUSES = ("AVAILABLE", "FULL", "CANCELLED")


class ScheduleBase(BaseModel):
    doctor_id    : UUID
    room_id      : UUID
    start_time   : datetime = Field(..., examples=["2025-06-01T08:00:00"])
    end_time     : datetime = Field(..., examples=["2025-06-01T12:00:00"])
    max_patients : int      = Field(1, ge=1, le=100)

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.start_time < datetime.now():
            raise ValueError("Cannot create a schedule in the past")
        return self


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    room_id      : Optional[UUID]     = None
    start_time   : Optional[datetime] = None
    end_time     : Optional[datetime] = None
    max_patients : Optional[int]      = Field(None, ge=1, le=100)
    status       : Optional[str]      = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValueError("end_time must be after start_time")
        return self


class ScheduleResponse(ScheduleBase):
    schedule_id    : UUID
    current_booked : int
    status         : str

    model_config = {"from_attributes": True}


class ScheduleAvailabilityResponse(BaseModel):
    """Slim response for public-facing availability check."""
    schedule_id    : UUID
    doctor_id      : UUID
    room_id        : UUID
    start_time     : datetime
    end_time       : datetime
    slots_remaining: int
    status         : str

    model_config = {"from_attributes": True}


# Resolve forward refs
DoctorWithSchedules.model_rebuild()