from uuid import UUID
from decimal import Decimal
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ── Medication ────────────────────────────────────

class MedicationCreate(BaseModel):
    med_code          : str     = Field(..., max_length=50)
    med_name          : str     = Field(..., max_length=255)
    active_ingredient : Optional[str] = None
    unit              : str     = Field(..., max_length=20)
    price             : Decimal = Field(..., ge=0)
    is_bhyt_covered   : bool    = True

class MedicationUpdate(BaseModel):
    med_name          : Optional[str]     = None
    active_ingredient : Optional[str]     = None
    price             : Optional[Decimal] = Field(None, ge=0)
    is_bhyt_covered   : Optional[bool]    = None
    is_active         : Optional[bool]    = None

class MedicationResponse(MedicationCreate):
    medication_id : UUID
    is_active     : bool
    model_config = {"from_attributes": True}


# ── Inventory ─────────────────────────────────────

class InventoryCreate(BaseModel):
    medication_id   : UUID
    batch_number    : str  = Field(..., max_length=50)
    quantity        : int  = Field(..., ge=0)
    expiration_date : date

class InventoryAdjust(BaseModel):
    """Cộng hoặc trừ số lượng (dương = nhập kho, âm = xuất kho)."""
    delta    : int
    reason   : Optional[str] = None

class InventoryResponse(InventoryCreate):
    inventory_id : UUID
    updated_at   : datetime
    model_config = {"from_attributes": True}


# ── Prescription ──────────────────────────────────

class PrescriptionItemCreate(BaseModel):
    medication_id      : UUID
    quantity           : int  = Field(..., ge=1)
    dosage_instruction : Optional[str] = None

class PrescriptionCreate(BaseModel):
    record_id : UUID
    doctor_id : UUID
    notes     : Optional[str] = None
    items     : List[PrescriptionItemCreate] = Field(..., min_length=1)

class PrescriptionSign(BaseModel):
    doctor_signature_hash : str = Field(..., min_length=64, max_length=64)

class PrescriptionItemResponse(BaseModel):
    item_id            : UUID
    medication_id      : UUID
    med_name           : Optional[str] = None
    quantity           : int
    dosage_instruction : Optional[str]
    model_config = {"from_attributes": True}

class PrescriptionResponse(BaseModel):
    prescription_id       : UUID
    record_id             : UUID
    doctor_id             : UUID
    notes                 : Optional[str]
    doctor_signature_hash : Optional[str]
    signed_at             : Optional[datetime]
    created_at            : datetime
    items                 : List[PrescriptionItemResponse] = []
    model_config = {"from_attributes": True}