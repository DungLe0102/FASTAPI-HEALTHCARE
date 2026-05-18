from uuid import UUID
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from app.models.billing import Billing, PaymentTransaction
from app.models.order import Order
from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.schemas.report import (
    RevenueSummaryResponse,
    DoctorRevenueResponse,
    DoctorRevenueItem,
    MedicationRevenueResponse,
    MedicationRevenueItem,
    PatientFinancialSummary
)

def get_total_revenue(db: Session, start_date: date, end_date: date) -> RevenueSummaryResponse:
    # Doanh thu từ khám bệnh (các hóa đơn đã thanh toán một phần hoặc toàn bộ)
    appointments_rev = db.query(func.sum(PaymentTransaction.amount)).join(Billing).filter(
        PaymentTransaction.transaction_status == "SUCCESS",
        func.date(PaymentTransaction.payment_date) >= start_date,
        func.date(PaymentTransaction.payment_date) <= end_date
    ).scalar() or Decimal("0")

    # Doanh thu từ Order (Pharmacy và BHYT_EXTENSION)
    orders = db.query(Order.order_type, func.sum(Order.total_amount)).filter(
        Order.status == "PAID",
        func.date(Order.created_at) >= start_date,
        func.date(Order.created_at) <= end_date
    ).group_by(Order.order_type).all()

    pharmacy_rev = Decimal("0")
    bhyt_rev = Decimal("0")
    
    for o_type, total in orders:
        if o_type == "PHARMACY":
            pharmacy_rev = total
        elif o_type == "BHYT_EXTENSION":
            bhyt_rev = total

    total_rev = appointments_rev + pharmacy_rev + bhyt_rev

    return RevenueSummaryResponse(
        total_revenue=total_rev,
        total_appointments_revenue=appointments_rev,
        total_pharmacy_revenue=pharmacy_rev,
        total_bhyt_extension_revenue=bhyt_rev,
        period_start=start_date,
        period_end=end_date
    )

def get_doctor_revenues(db: Session, start_date: date, end_date: date) -> DoctorRevenueResponse:
    appointments = db.query(
        Doctor.doctor_id,
        Doctor.first_name,
        Doctor.last_name,
        Doctor.specialization,
        func.count(Appointment.appointment_id).label("completed_appointments"),
        func.sum(Billing.total_amount).label("total_earnings")
    ).select_from(Doctor).join(Appointment).join(Billing).filter(
        Appointment.status == "COMPLETED",
        Billing.billing_status.in_(["PAID", "PARTIAL"]),
        func.date(Appointment.appointment_date) >= start_date,
        func.date(Appointment.appointment_date) <= end_date
    ).group_by(Doctor.doctor_id).all()

    items = []
    for appt in appointments:
        items.append(DoctorRevenueItem(
            doctor_id=appt.doctor_id,
            doctor_name=f"{appt.last_name} {appt.first_name}",
            specialization=appt.specialization,
            completed_appointments=appt.completed_appointments,
            total_earnings=appt.total_earnings or Decimal("0")
        ))
    
    return DoctorRevenueResponse(
        period_start=start_date,
        period_end=end_date,
        doctors=items
    )

def get_medication_revenues(db: Session, start_date: date, end_date: date) -> MedicationRevenueResponse:
    orders = db.query(Order).filter(
        Order.order_type == "PHARMACY",
        Order.status == "PAID",
        func.date(Order.created_at) >= start_date,
        func.date(Order.created_at) <= end_date
    ).all()

    med_sales = {}
    for order in orders:
        items = order.order_metadata.get("items", [])
        for item in items:
            med_id = item["medication_id"]
            if med_id not in med_sales:
                med_sales[med_id] = {
                    "med_name": item["med_name"],
                    "qty": 0,
                    "rev": Decimal("0")
                }
            med_sales[med_id]["qty"] += item["quantity"]
            med_sales[med_id]["rev"] += Decimal(str(item["line_total"]))

    results = []
    for med_id, data in med_sales.items():
        results.append(MedicationRevenueItem(
            medication_id=UUID(med_id),
            medication_name=data["med_name"],
            quantity_sold=data["qty"],
            total_revenue=data["rev"]
        ))
        
    return MedicationRevenueResponse(
        period_start=start_date,
        period_end=end_date,
        medications=results
    )

def get_patient_financials(db: Session, patient_id: UUID) -> PatientFinancialSummary:
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Total Paid from Billings (SUCCESS only)
    billing_paid = db.query(func.sum(PaymentTransaction.amount)).join(Billing).join(Appointment).filter(
        Appointment.patient_id == patient_id,
        PaymentTransaction.transaction_status == "SUCCESS"
    ).scalar() or Decimal("0")

    # Total Refunded
    billing_refunded = db.query(func.sum(PaymentTransaction.amount)).join(Billing).join(Appointment).filter(
        Appointment.patient_id == patient_id,
        PaymentTransaction.transaction_status == "REFUNDED"
    ).scalar() or Decimal("0")

    # Total from Orders (PAID)
    order_paid = db.query(func.sum(Order.total_amount)).filter(
        Order.patient_id == patient_id,
        Order.status == "PAID"
    ).scalar() or Decimal("0")

    # Total Pending from Billings
    billing_pending = db.query(func.sum(Billing.patient_paid_amount)).join(Appointment).filter(
        Appointment.patient_id == patient_id,
        Billing.billing_status.in_(["UNPAID", "PARTIAL"])
    ).scalar() or Decimal("0")
    
    # Need to subtract what they already paid for partials
    billing_already_paid_partial = db.query(func.sum(PaymentTransaction.amount)).join(Billing).join(Appointment).filter(
        Appointment.patient_id == patient_id,
        Billing.billing_status == "PARTIAL",
        PaymentTransaction.transaction_status == "SUCCESS"
    ).scalar() or Decimal("0")
    
    total_pending = billing_pending - billing_already_paid_partial

    return PatientFinancialSummary(
        patient_id=patient.patient_id,
        patient_name=f"{patient.last_name} {patient.first_name}",
        total_paid=billing_paid + order_paid,
        total_refunded=billing_refunded,
        pending_amount=max(Decimal("0"), total_pending)
    )
