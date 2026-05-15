from tests.base import BaseTestCase
from app.services import doctor_service
from app.models.department import Department
from app.schemas.doctor import DoctorCreate
from fastapi import HTTPException
import uuid

class TestDoctorService(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Tạo khoa mới cho mỗi test để tránh trùng mã
        unique_code = f"K_TEST_{uuid.uuid4().hex[:6]}"
        self.dept = Department(department_code=unique_code, department_name="Khoa Test")
        self.db.add(self.dept)
        self.db.commit()
        self.db.refresh(self.dept)

    def test_create_doctor_success(self):
        payload = DoctorCreate(
            first_name="Tran",
            last_name="Van B",
            specialization="Cardiology",
            department_id=self.dept.department_id,
            hourly_consultation_fee=500000
        )
        
        doctor = doctor_service.create_doctor(self.db, payload)
        self.assertEqual(doctor.first_name, "Tran")
        self.assertEqual(doctor.department_id, self.dept.department_id)

    def test_create_doctor_invalid_dept_fails(self):
        payload = DoctorCreate(
            first_name="Dr",
            last_name="Fail",
            specialization="None",
            department_id=uuid.uuid4(), # Random UUID không tồn tại
            hourly_consultation_fee=100000
        )
        
        with self.assertRaises(HTTPException) as cm:
            doctor_service.create_doctor(self.db, payload)
        
        self.assertEqual(cm.exception.status_code, 404)
