from tests.base import BaseTestCase
from app.services import department_service
from app.models.department import Department, Room
from app.schemas.department import DepartmentUpdate, RoomCreate
import uuid

class TestDepartmentService(BaseTestCase):
    def test_init_standard_departments(self):
        # Test khởi tạo hạng III (ít khoa nhất cho nhanh)
        depts = department_service.init_standard_departments(self.db, "III")
        self.assertGreater(len(depts), 0)
        
        # Kiểm tra tính idempotent (gọi lại không lỗi, không tạo trùng)
        depts_again = department_service.init_standard_departments(self.db, "III")
        self.assertEqual(len(depts_again), 0)

    def test_get_all_departments(self):
        # Setup
        self.db.add(Department(department_code="TEST1", department_name="Khoa Test 1"))
        self.db.add(Department(department_code="TEST2", department_name="Khoa Test 2", is_active=False))
        self.db.commit()

        # Test active_only=True
        active_depts = department_service.get_all_departments(self.db, active_only=True)
        self.assertEqual(len(active_depts), 1)
        self.assertEqual(active_depts[0].department_code, "TEST1")

        # Test search
        search_results = department_service.get_all_departments(self.db, search="Test 2")
        self.assertEqual(len(search_results), 1)
        self.assertEqual(search_results[0].department_code, "TEST2")

    def test_deactivate_department(self):
        dept = Department(department_code="DEACT", department_name="To be deactivated")
        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)

        updated_dept = department_service.deactivate_department(self.db, dept.department_id)
        self.assertFalse(updated_dept.is_active)

    def test_create_room_in_inactive_dept_fails(self):
        dept = Department(department_code="INACT", department_name="Inactive", is_active=False)
        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            payload = RoomCreate(room_number="101", department_id=dept.department_id)
            department_service.create_room(self.db, payload)
        
        self.assertEqual(cm.exception.status_code, 400)
