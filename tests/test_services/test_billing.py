from tests.base import BaseTestCase
from app.services import billing_service, appointment_service, patient_service, doctor_service
from app.models.account import Account
from app.models.department import Department, Room
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.schemas.billing import BillingCreate, PaymentCreate, PaymentStatusUpdate, VietQRWebhookPayload
from app.schemas.appointment import AppointmentCreate
from app.schemas.doctor import DoctorCreate, ScheduleCreate
from app.schemas.patient import PatientCreate
from fastapi import HTTPException
from datetime import datetime, timedelta, date
import uuid

class TestBillingService(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Setup basic data
        self.patient_id = uuid.uuid4()
        self.db.add(Account(account_id=self.patient_id, email="p@t.com", password_hash="h", role="PATIENT"))
        patient_service.create_patient(self.db, PatientCreate(
            first_name="A", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345678", cccd="001090123456", address="H"
        ), patient_id=self.patient_id)

        self.dept = Department(department_code="K_NOI", department_name="Khoa Noi")
        self.db.add(self.dept)
        self.db.commit()

        self.doctor = doctor_service.create_doctor(self.db, DoctorCreate(
            first_name="Dr", last_name="Test", specialization="General",
            department_id=self.dept.department_id, hourly_consultation_fee=100000
        ))

        self.room = Room(room_number="101", department_id=self.dept.department_id)
        self.db.add(self.room)
        self.db.commit()

        self.schedule = doctor_service.create_schedule(self.db, ScheduleCreate(
            doctor_id=self.doctor.doctor_id, room_id=self.room.room_id,
            start_time=datetime.now() + timedelta(days=1),
            end_time=datetime.now() + timedelta(days=1, hours=4),
            max_patients=10
        ))

        self.appt = appointment_service.create_appointment(self.db, AppointmentCreate(
            patient_id=self.patient_id, schedule_id=self.schedule.schedule_id
        ))
        self.bill = billing_service.get_billing_by_appointment(self.db, self.appt.appointment_id)

    def test_payment_lifecycle(self):
        # Create payment transaction
        txn = billing_service.create_payment(self.db, PaymentCreate(
            billing_id=self.bill.billing_id,
            payment_method="CASH",
            amount=100000
        ))
        self.assertEqual(txn.transaction_status, "PENDING")

        # Update to SUCCESS
        billing_service.update_payment_status(self.db, txn.transaction_id, PaymentStatusUpdate(
            transaction_status="SUCCESS",
            gateway_reference_id="REF123"
        ))
        
        # Check bill status
        self.db.refresh(self.bill)
        self.assertEqual(self.bill.billing_status, "PAID")
        
        # Check appointment status sync
        self.db.refresh(self.appt)
        self.assertEqual(self.appt.status, "SCHEDULED")

    def test_vietqr_webhook(self):
        # Generate QR to create PENDING transaction
        qr_data = billing_service.generate_vietqr_payment(self.db, self.bill.billing_id)
        txn_id = qr_data["transaction_id"]
        
        # Simulate Webhook
        from app.schemas.billing import VietQRWebhookData
        # Actually I saw it is VietQRWebhookData
        payload = VietQRWebhookPayload(
            error=0,
            message="Success",
            data=[VietQRWebhookData(
                amount=100000,
                description=f"PAY {txn_id}",
                reference_number="REF_WEBHOOK"
            )]
        )
        billing_service.process_vietqr_webhook(self.db, payload)
        
        self.db.refresh(self.bill)
        self.assertEqual(self.bill.billing_status, "PAID")
