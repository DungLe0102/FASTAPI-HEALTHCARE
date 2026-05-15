from uuid import UUID
from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import re           


# ──────────────────────────────────────────
# PATIENT SCHEMAS
# ──────────────────────────────────────────

class PatientBase(BaseModel):
    first_name : str  = Field(..., max_length=100, examples=["Nguyen"])
    last_name  : str  = Field(..., max_length=100, examples=["Van A"])
    dob        : date = Field(..., examples=["1990-05-15"])
    gender     : Optional[Literal["MALE", "FEMALE", "OTHER"]] = None
    phone      : Optional[str] = Field(None, max_length=20)
    cccd       : Optional[str] = Field(None, max_length=12)
    address    : Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v and not re.match(r"^[0-9+\-\s]{7,20}$", v):
            raise ValueError("Invalid phone number format")
        return v
    @field_validator("cccd")
    @classmethod
    def validate_cccd(cls, v):
        if v and not re.match(r"^[0-9]{9,12}$", v):
            raise ValueError("Invalid CCCD format")
        return v    

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, v):
        if v >= date.today():
            raise ValueError("Date of birth must be in the past")
        return v


class PatientCreate(PatientBase):
    model_config = {
        "json_schema_extra": {
            "example": {
                "first_name": "Van A",
                "last_name": "Nguyen",
                "dob": "1990-01-01",
                "gender": "MALE",
                "phone": "0912345678",
                "cccd": "001090123456",
                "address": "123 Le Loi, District 1, HCMC"
            }
        }
    }


class PatientUpdate(BaseModel):
    first_name : Optional[str]  = Field(None, max_length=100)
    last_name  : Optional[str]  = Field(None, max_length=100)
    dob        : Optional[date] = Field(None)
    gender     : Optional[Literal["MALE", "FEMALE", "OTHER"]] = None
    phone      : Optional[str]  = Field(None, max_length=20)
    cccd       : Optional[str]  = Field(None, max_length=12)
    address    : Optional[str]  = None


class PatientResponse(PatientBase):
    patient_id : UUID
    created_at : datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "patient_id": "c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39",
                "first_name": "Van A",
                "last_name": "Nguyen",
                "dob": "1990-01-01",
                "gender": "MALE",
                "phone": "0912345678",
                "created_at": "2026-05-08T14:00:00Z"
            }
        }
    )


class PatientProfileResponse(PatientResponse):
    @field_validator("phone", "cccd", mode="after")
    @classmethod
    def mask_data(cls, v: str | None) -> str | None:
        if v and len(v) > 4:
            return v[:2] + "*" * (len(v) - 4) + v[-2:]
        return v


class PatientWithBHYT(PatientResponse):
    bhyt_records: List["BHYTResponse"] = []


# ──────────────────────────────────────────
# BHYT SCHEMAS
# ──────────────────────────────────────────

BHYT_CODE_PATTERN = re.compile(r"^[A-Z]{2}\d{13}$")   # Chuẩn mã BHYT Việt Nam

class BHYTBase(BaseModel):
    bhyt_code               : str  = Field(..., max_length=15, examples=["HS4010123456789"])
    registered_hospital_code: Optional[str] = Field(None, max_length=20, examples=["01001"])
    valid_from              : date = Field(..., examples=["2026-01-01"])
    valid_to                : date = Field(..., examples=["2026-12-31"])

    @field_validator("bhyt_code")
    @classmethod
    def validate_bhyt_code(cls, v):
        if not BHYT_CODE_PATTERN.match(v):
            raise ValueError(
                "BHYT code must be 2 uppercase letters followed by 13 digits (e.g. HS4010123456789)"
            )
        return v

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to must be >= valid_from")
        return self


class BHYTCreate(BHYTBase):
    patient_id: UUID = Field(..., examples=["c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39"])


class BHYTUpdate(BaseModel):
    registered_hospital_code: Optional[str] = None
    valid_from              : Optional[date] = None
    valid_to                : Optional[date] = None
    is_active               : Optional[bool] = None


class BHYTVerifyUpdate(BaseModel):
    """Used by admin/system to update check_status after portal verification."""
    check_status: Literal["PENDING", "VERIFIED", "FAILED"]


class BHYTResponse(BHYTBase):
    bhyt_id      : UUID
    patient_id   : UUID
    is_active    : bool
    check_status : str
    created_at   : datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "bhyt_id": "e3f7g3e2-0fcd-6ge0-b6e1-23f55fgfd851",
                "patient_id": "c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39",
                "bhyt_code": "HS4010123456789",
                "is_active": True,
                "check_status": "VERIFIED",
                "valid_to": "2026-12-31"
            }
        }
    )


# ──────────────────────────────────────────
# CONSENT SCHEMAS
# ──────────────────────────────────────────

CONSENT_TYPES = Literal[
    "DATA_PROCESSING",
    "MARKETING",
    "RESEARCH",
    "THIRD_PARTY_SHARE",
]

class ConsentCreate(BaseModel):
    patient_id   : UUID = Field(..., examples=["c1dfb1c0-8dab-4fa8-94c9-01f33fde8b39"])
    consent_type : CONSENT_TYPES = Field(..., examples=["DATA_PROCESSING"])
    is_granted   : bool = True
    ip_address   : Optional[str] = Field(None, max_length=45)
    user_agent   : Optional[str] = None


class ConsentResponse(BaseModel):
    consent_id   : UUID
    patient_id   : UUID
    consent_type : str
    is_granted   : bool
    ip_address   : Optional[str]
    timestamp    : datetime

    model_config = ConfigDict(from_attributes=True)


# Resolve forward refs
PatientWithBHYT.model_rebuild()
