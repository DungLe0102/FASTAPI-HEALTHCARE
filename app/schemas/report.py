from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


class DateRangeRequest(BaseModel):
    start_date: date
    end_date: date


class RevenueSummaryResponse(BaseModel):
    total_revenue: Decimal
    total_appointments_revenue: Decimal
    total_pharmacy_revenue: Decimal
    total_bhyt_extension_revenue: Decimal
    period_start: date
    period_end: date


class DoctorRevenueItem(BaseModel):
    doctor_id: UUID
    doctor_name: str
    specialization: Optional[str]
    completed_appointments: int
    total_earnings: Decimal


class DoctorRevenueResponse(BaseModel):
    period_start: date
    period_end: date
    doctors: List[DoctorRevenueItem]


class MedicationRevenueItem(BaseModel):
    medication_id: UUID
    medication_name: str
    quantity_sold: int
    total_revenue: Decimal


class MedicationRevenueResponse(BaseModel):
    period_start: date
    period_end: date
    medications: List[MedicationRevenueItem]


class PatientFinancialSummary(BaseModel):
    patient_id: UUID
    patient_name: str
    total_paid: Decimal
    total_refunded: Decimal
    pending_amount: Decimal
