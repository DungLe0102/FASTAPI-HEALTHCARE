from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_roles, get_current_account
from app.models.account import Account
from app.schemas.report import (
    RevenueSummaryResponse,
    DoctorRevenueResponse,
    MedicationRevenueResponse,
    PatientFinancialSummary
)
from app.services import report_service

router = APIRouter(prefix="/api/v1/reports", tags=["7. Reports & Statistics"])

@router.get(
    "/revenue/summary",
    response_model=RevenueSummaryResponse,
    summary="[ADMIN] Xem tổng doanh thu",
)
def get_revenue_summary(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    _: Account = Depends(require_roles("ADMIN")),
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")
    return report_service.get_total_revenue(db, start_date, end_date)


@router.get(
    "/revenue/doctors",
    response_model=DoctorRevenueResponse,
    summary="[ADMIN] Xem doanh thu do bác sĩ mang lại",
)
def get_doctor_revenue(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    _: Account = Depends(require_roles("ADMIN")),
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")
    return report_service.get_doctor_revenues(db, start_date, end_date)


@router.get(
    "/revenue/medications",
    response_model=MedicationRevenueResponse,
    summary="[ADMIN] Xem doanh thu từng loại thuốc",
)
def get_medication_revenue(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    _: Account = Depends(require_roles("ADMIN")),
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")
    return report_service.get_medication_revenues(db, start_date, end_date)


@router.get(
    "/financials/patients/{patient_id}",
    response_model=PatientFinancialSummary,
    summary="Xem tổng quan tài chính của bệnh nhân",
)
def get_patient_financials(
    patient_id: UUID,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    Bệnh nhân xem tổng số tiền đã trả, được hoàn, hoặc còn nợ.
    Admin được quyền xem của tất cả mọi người.
    """
    if current_acc.role == "PATIENT" and current_acc.account_id != patient_id:
        raise HTTPException(status_code=403, detail="You can only view your own financials")
    
    return report_service.get_patient_financials(db, patient_id)
