from tests.base import BaseTestCase
from app.services import appointment_service, patient_service, doctor_service, department_service
from app.models.account import Account
from app.models.department import Department, Room
from app.models.doctor import Doctor, DoctorSchedule
from app.models.patient import Patient
from app.schemas.appointment import AppointmentCreate, AppointmentStatusUpdate
from app.schemas.doctor import DoctorCreate, ScheduleCreate
from app.schemas.patient import PatientCreate
from fastapi import HTTPException
from datetime import datetime, timedelta, date
import uuid

class TestAppointmentService(BaseTestCase):
    def setUp(self):
        super().setUp()
        # 1. Setup Patient
        self.patient_id = uuid.uuid4()
        self.db.add(Account(account_id=self.patient_id, email="p@t.com", password_hash="h", role="PATIENT"))
        patient_service.create_patient(self.db, PatientCreate(
            first_name="A", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345678", cccd="001090123456", address="H"
        ), patient_id=self.patient_id)

        # 2. Setup Department
        self.dept = Department(department_code="K_NOI", department_name="Khoa Noi")
        self.db.add(self.dept)
        self.db.commit()

        # 3. Setup Room
        self.room = Room(room_number="101", department_id=self.dept.department_id)
        self.db.add(self.room)
        self.db.commit()

        # 4. Setup Doctor
        self.doctor = doctor_service.create_doctor(self.db, DoctorCreate(
            first_name="Dr", last_name="Test", specialization="General",
            department_id=self.dept.department_id, hourly_consultation_fee=100000
        ))
        print(f"DEBUG: Doctor fee = {self.doctor.hourly_consultation_fee}")

        # 5. Setup Schedule (Future)
        self.start_time = datetime.now() + timedelta(days=1)
        self.schedule = doctor_service.create_schedule(self.db, ScheduleCreate(
            doctor_id=self.doctor.doctor_id,
            room_id=self.room.room_id,
            start_time=self.start_time,
            end_time=self.start_time + timedelta(hours=4),
            max_patients=2
        ))

    def test_create_appointment_success(self):
        payload = AppointmentCreate(
            patient_id=self.patient_id,
            schedule_id=self.schedule.schedule_id,
            symptoms="Headache"
        )
        appt = appointment_service.create_appointment(self.db, payload)
        self.assertEqual(appt.status, "PENDING_PAYMENT")
        self.assertIsNotNone(appt.billing_id)
        self.assertIn("vietqr.io", appt.payment_qr_url)
        
        # Check slot updated
        self.db.refresh(self.schedule)
        self.assertEqual(self.schedule.current_booked, 1)

    def test_create_appointment_full_fails(self):
        # Book all slots
        payload = AppointmentCreate(patient_id=self.patient_id, schedule_id=self.schedule.schedule_id)
        appointment_service.create_appointment(self.db, payload)
        
        # Create second patient
        p2_id = uuid.uuid4()
        self.db.add(Account(account_id=p2_id, email="p2@t.com", password_hash="h", role="PATIENT"))
        patient_service.create_patient(self.db, PatientCreate(
            first_name="B", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345679", cccd="001090222222", address="H"
        ), patient_id=p2_id)
        
        # Second appointment
        appointment_service.create_appointment(self.db, AppointmentCreate(patient_id=p2_id, schedule_id=self.schedule.schedule_id))
        
        # Third appointment (Schedule max_patients=2)
        p3_id = uuid.uuid4()
        self.db.add(Account(account_id=p3_id, email="p3@t.com", password_hash="h", role="PATIENT"))
        patient_service.create_patient(self.db, PatientCreate(
            first_name="C", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345670", cccd="001090333333", address="H"
        ), patient_id=p3_id)
        
        with self.assertRaises(HTTPException) as cm:
            appointment_service.create_appointment(self.db, AppointmentCreate(patient_id=p3_id, schedule_id=self.schedule.schedule_id))
        self.assertEqual(cm.exception.status_code, 409)

    def test_status_transition_invalid_fails(self):
        payload = AppointmentCreate(patient_id=self.patient_id, schedule_id=self.schedule.schedule_id)
        appt = appointment_service.create_appointment(self.db, payload)
        
        # Cannot go from PENDING_PAYMENT to COMPLETED
        with self.assertRaises(HTTPException) as cm:
            appointment_service.update_status(self.db, appt.appointment_id, AppointmentStatusUpdate(status="COMPLETED"))
        self.assertEqual(cm.exception.status_code, 400)
