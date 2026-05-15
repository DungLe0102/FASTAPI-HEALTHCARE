from uuid import UUID
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict


# ── SCHEMAS ───────────────────────────────────────

class BillingCreate(BaseModel):
    appointment_id      : UUID
    total_amount        : Decimal = Field(..., ge=0)
    bhyt_covered_amount : Decimal = Field(Decimal("0"), ge=0)

    @model_validator(mode="after")
    def calc_patient_amount(self):
        # patient_paid = total - bhyt
        diff = self.total_amount - self.bhyt_covered_amount
        if diff < 0:
            raise ValueError("bhyt_covered_amount cannot exceed total_amount")
        self.patient_paid_amount = diff
        return self

    patient_paid_amount : Decimal = Decimal("0")   # computed above


class BillingResponse(BaseModel):
    billing_id          : UUID
    appointment_id      : UUID
    total_amount        : Decimal
    bhyt_covered_amount : Decimal
    patient_paid_amount : Decimal
    billing_status      : str
    created_at          : datetime
    model_config = ConfigDict(from_attributes=True)


class PaymentCreate(BaseModel):
    billing_id           : UUID
    payment_method       : Literal["CASH", "VIETQR", "BANK_TRANSFER"] = "VIETQR"
    amount               : Decimal = Field(..., gt=0)
    gateway_reference_id : Optional[str] = None


class PaymentStatusUpdate(BaseModel):
    transaction_status   : Literal["SUCCESS", "FAILED"]
    gateway_reference_id : Optional[str] = None


class PaymentResponse(BaseModel):
    transaction_id       : UUID
    billing_id           : UUID
    payment_method       : str
    amount               : Decimal
    gateway_reference_id : Optional[str]
    transaction_status   : str
    payment_date         : Optional[datetime]
    model_config = ConfigDict(from_attributes=True)

# ── VIETQR SCHEMAS ────────────────────────────────

class VietQRWebhookData(BaseModel):
    amount: Decimal
    description: str # Chứa mã transaction_id để đối soát
    reference_number: str # Mã tham chiếu từ ngân hàng (Gateway Ref)

class VietQRWebhookPayload(BaseModel):
    error: int
    message: str
    data: List[VietQRWebhookData]


class VietQRRefundRequest(BaseModel):
    transaction_id: UUID
    amount: Decimal = Field(..., gt=0)
    content: str

class VietQRRefundResponse(BaseModel):
    status: str
    message: str


# ── DOCTOR PAYOUT SCHEMAS ─────────────────────────

class DoctorPayoutBase(BaseModel):
    doctor_id    : UUID
    amount       : Decimal = Field(..., ge=0)
    payout_date  : date
    period_start : date
    period_end   : date
    notes        : Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self) -> "DoctorPayoutBase":
        if self.period_start > self.period_end:
            raise ValueError("period_start must be before or equal to period_end")
        return self


class DoctorPayoutCreate(DoctorPayoutBase):
    pass


class DoctorPayoutUpdate(BaseModel):
    status: Literal["PENDING", "PAID", "CANCELLED"]
    notes : Optional[str] = None


class DoctorPayoutRead(DoctorPayoutBase):
    payout_id  : UUID
    status     : str
    created_at : datetime
    
    model_config = ConfigDict(from_attributes=True)


class DoctorEarningsCalculate(BaseModel):
    doctor_id    : UUID
    period_start : date
    period_end   : date


class DoctorEarningsResponse(BaseModel):
    doctor_id              : UUID
    doctor_name            : str
    period_start           : date
    period_end             : date
    completed_appointments : int
    total_earnings         : Decimal