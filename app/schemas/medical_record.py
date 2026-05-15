from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
import re


# ─────────────────────────────────────────────
# ICD-10 VALIDATOR (pattern chuẩn WHO)
# ─────────────────────────────────────────────
ICD10_RE = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")


# ─────────────────────────────────────────────
# CLINICAL SERVICE SCHEMAS
# ─────────────────────────────────────────────

class ClinicalServiceBase(BaseModel):
    service_code    : str     = Field(..., max_length=50,  examples=["XN001"])
    service_name    : str     = Field(..., max_length=255, examples=["Complete Blood Count"])
    price           : Decimal = Field(..., ge=0,           examples=[150000])
    is_bhyt_covered : bool    = True
    is_active       : bool    = True


class ClinicalServiceCreate(ClinicalServiceBase):
    pass


class ClinicalServiceUpdate(BaseModel):
    service_name    : Optional[str]     = None
    price           : Optional[Decimal] = Field(None, ge=0)
    is_bhyt_covered : Optional[bool]    = None
    is_active       : Optional[bool]    = None


class ClinicalServiceResponse(ClinicalServiceBase):
    service_id: UUID
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# RECORD SERVICE (line items)
# ─────────────────────────────────────────────

class RecordServiceCreate(BaseModel):
    service_id   : UUID
    quantity     : int            = Field(1, ge=1)
    actual_price : Optional[Decimal] = Field(
        None, ge=0,
        description="Override price; defaults to catalogue price if omitted",
    )


class RecordServiceResponse(BaseModel):
    record_service_id : UUID
    service_id        : UUID
    service_name      : Optional[str] = None
    quantity          : int
    actual_price      : Decimal
    created_at        : datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# MEDICAL RECORD SCHEMAS
# ─────────────────────────────────────────────

class MedicalRecordCreate(BaseModel):
    appointment_id : UUID
    icd10_code     : Optional[str] = Field(None, max_length=10, examples=["J06.9"])
    diagnosis      : str           = Field(..., min_length=3)
    symptoms       : Optional[str] = None
    treatment_plan : Optional[str] = None
    services       : List[RecordServiceCreate] = []

    @field_validator("icd10_code")
    @classmethod
    def validate_icd10(cls, v):
        if v and not ICD10_RE.match(v):
            raise ValueError("Invalid ICD-10 code. Expected format: J06 or J06.9")
        return v


class MedicalRecordUpdate(BaseModel):
    icd10_code     : Optional[str] = Field(None, max_length=10)
    diagnosis      : Optional[str] = Field(None, min_length=3)
    symptoms       : Optional[str] = None
    treatment_plan : Optional[str] = None

    @field_validator("icd10_code")
    @classmethod
    def validate_icd10(cls, v):
        if v and not ICD10_RE.match(v):
            raise ValueError("Invalid ICD-10 code format")
        return v


class SignRecordRequest(BaseModel):
    """
    Bác sĩ ký hồ sơ.
    doctor_secret → SHA-256 → doctor_signature_hash.
    Production: thay bằng private key PKI / HSM.
    """
    doctor_secret : str            = Field(..., min_length=8)
    ma_lk         : Optional[str] = Field(None, max_length=50,description="Mã liên kết cổng BHYT")


class MedicalRecordResponse(BaseModel):
    record_id             : UUID
    appointment_id        : UUID
    ma_lk                 : Optional[str]
    icd10_code            : Optional[str]
    diagnosis             : str
    symptoms              : Optional[str]
    treatment_plan        : Optional[str]
    doctor_signature_hash : Optional[str]
    signed_at             : Optional[datetime]
    created_at            : datetime
    services              : List[RecordServiceResponse] = []

    model_config = {"from_attributes": True}