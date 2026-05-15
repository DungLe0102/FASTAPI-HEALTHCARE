from tests.base import BaseTestCase
from app.services import patient_service
from app.models.account import Account
from app.models.patient import Patient, PatientBHYT
from app.schemas.patient import PatientCreate, PatientUpdate, BHYTCreate
from fastapi import HTTPException
from datetime import date, timedelta
import uuid

class TestPatientService(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Tạo account cho patient
        self.patient_id = uuid.uuid4()
        self.account = Account(
            account_id=self.patient_id,
            email="patient@test.com",
            password_hash="hash",
            role="PATIENT"
        )
        self.db.add(self.account)
        self.db.commit()

    def test_create_patient_success(self):
        payload = PatientCreate(
            first_name="Van A",
            last_name="Nguyen",
            dob=date(1990, 1, 1),
            gender="MALE",
            phone="0912345678",
            cccd="001090123456",
            address="Hanoi"
        )
        patient = patient_service.create_patient(self.db, payload, patient_id=self.patient_id)
        self.assertEqual(patient.first_name, "Van A")
        self.assertEqual(patient.phone, "0912345678")
        
        # Kiểm tra sync identity
        self.db.refresh(self.account)
        self.assertEqual(self.account.full_name, "Nguyen Van A")

    def test_create_patient_duplicate_phone_fails(self):
        payload1 = PatientCreate(
            first_name="A", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345678", cccd="001090111111", address="H"
        )
        patient_service.create_patient(self.db, payload1, patient_id=self.patient_id)
        
        account2_id = uuid.uuid4()
        self.db.add(Account(account_id=account2_id, email="p2@t.com", password_hash="h", role="PATIENT"))
        self.db.commit()
        
        payload2 = PatientCreate(
            first_name="B", last_name="N", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345678", cccd="001090222222", address="H"
        )
        with self.assertRaises(HTTPException) as cm:
            patient_service.create_patient(self.db, payload2, patient_id=account2_id)
        self.assertEqual(cm.exception.status_code, 409)

    def test_bhyt_lifecycle(self):
        # Create patient
        payload = PatientCreate(
            first_name="Van A", last_name="Nguyen", dob=date(1990, 1, 1),
            gender="MALE", phone="0912345678", cccd="001090123456", address="Hanoi"
        )
        patient_service.create_patient(self.db, payload, patient_id=self.patient_id)
        
        # Create BHYT
        bhyt_payload = BHYTCreate(
            patient_id=self.patient_id,
            bhyt_code="GD1234567890123",
            registered_hospital_code="01001",
            valid_from=date.today() - timedelta(days=10),
            valid_to=date.today() + timedelta(days=355)
        )
        bhyt = patient_service.create_bhyt(self.db, bhyt_payload)
        self.assertEqual(bhyt.bhyt_code, "GD1234567890123")
        
        # Verify BHYT
        from app.schemas.patient import BHYTVerifyUpdate
        patient_service.verify_bhyt(self.db, bhyt.bhyt_id, BHYTVerifyUpdate(check_status="VERIFIED"))
        
        # Get active BHYT
        active = patient_service.get_active_bhyt(self.db, self.patient_id)
        self.assertEqual(active.bhyt_id, bhyt.bhyt_id)
