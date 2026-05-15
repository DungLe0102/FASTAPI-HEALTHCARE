from tests.base import BaseTestCase
from app.services import medical_record_service, patient_service, doctor_service, department_service, appointment_service
from app.models.account import Account
from app.models.department import Department, Room
from app.models.doctor import Doctor, DoctorSchedule
from app.models.patient import Patient
from app.models.medical_record import ClinicalService
from app.schemas.medical_record import MedicalRecordCreate, ClinicalServiceCreate, RecordServiceCreate
from app.schemas.appointment import AppointmentCreate
from app.schemas.doctor import DoctorCreate, ScheduleCreate
from app.schemas.patient import PatientCreate
from fastapi import HTTPException
from datetime import datetime, timedelta, date
import uuid

class TestMedicalRecordService(BaseTestCase):
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
            department_id=self.dept.department_id, hourly_consultation_fee=0 # Free for easy test
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

        # Create Appointment
        self.appt = appointment_service.create_appointment(self.db, AppointmentCreate(
            patient_id=self.patient_id, schedule_id=self.schedule.schedule_id
        ))

    def test_create_medical_record_success(self):
        # Create a Clinical Service
        svc = medical_record_service.create_service(self.db, ClinicalServiceCreate(
            service_code="XUONG_KHOP", service_name="Chup X-Quang", price=200000
        ))

        # Phải chuyển trạng thái appointment sang IN_PROGRESS
        self.appt.status = "IN_PROGRESS"
        self.db.commit()

        payload = MedicalRecordCreate(
            appointment_id=self.appt.appointment_id,
            diagnosis="Dau chan",
            treatment_plan="Nghi ngoi",
            services=[RecordServiceCreate(service_id=svc.service_id, quantity=1)]
        )
        record = medical_record_service.create_record(self.db, payload)
        self.assertEqual(record.diagnosis, "Dau chan")
        self.assertEqual(len(record.services), 1)
        self.assertEqual(record.services[0].service_id, svc.service_id)

    def test_sign_medical_record(self):
        self.appt.status = "IN_PROGRESS"
        self.db.commit()

        payload = MedicalRecordCreate(
            appointment_id=self.appt.appointment_id,
            diagnosis="Test",
            treatment_plan="Test",
            services=[]
        )
        record = medical_record_service.create_record(self.db, payload)
        
        from app.schemas.medical_record import SignRecordRequest
        signed = medical_record_service.sign_record(self.db, record.record_id, SignRecordRequest(
            doctor_secret="my_secret"
        ), doctor_id=self.doctor.doctor_id)
        self.assertIsNotNone(signed.doctor_signature_hash)
        self.assertIsNotNone(signed.signed_at)
