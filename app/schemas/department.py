from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field


# ──────────────────────────────────────────
# DEPARTMENT SCHEMAS
# ──────────────────────────────────────────

class DepartmentBase(BaseModel):
    department_code: str = Field(..., max_length=20, examples=["CARD"])
    department_name: str = Field(..., max_length=100, examples=["Cardiology"])


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = Field(None, max_length=100)


class DepartmentResponse(DepartmentBase):
    department_id: UUID

    model_config = {"from_attributes": True}


class DepartmentWithRooms(DepartmentResponse):
    rooms: List["RoomResponse"] = []


# ──────────────────────────────────────────
# ROOM SCHEMAS
# ──────────────────────────────────────────

class RoomBase(BaseModel):
    room_number: str = Field(..., max_length=20, examples=["101"])
    room_type: Optional[str] = Field("CONSULTATION", max_length=50)
    is_active: Optional[bool] = True


class RoomCreate(RoomBase):
    department_id: UUID


class RoomUpdate(BaseModel):
    room_number: Optional[str] = Field(None, max_length=20)
    room_type: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class RoomResponse(RoomBase):
    room_id: UUID
    department_id: UUID

    model_config = {"from_attributes": True}


# Resolve forward reference
DepartmentWithRooms.model_rebuild()