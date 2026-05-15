import unittest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db import Base, get_db
from app.models.department import Department, Room
from app.models.account import Account
from app.models.doctor import Doctor, DoctorSchedule
from app.models.order import Order
from app.models.appointment import Appointment
# Import other models if needed
from app.security import get_current_account
from app.models.account import Account

from sqlalchemy.pool import StaticPool

# Setup SQLite in-memory for API testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency override
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Mock Account
def override_get_current_account():
    return Account(
        account_id=uuid.uuid4(),
        email="admin@test.com", 
        role="ADMIN", 
        full_name="Admin Test",
        is_active=True
    )

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_account] = override_get_current_account

class TestDepartmentAPI(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def test_init_standard_api(self):
        # Gọi endpoint khởi tạo khoa hạng III
        response = self.client.post("/api/v1/departments/init-standard/III")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertGreater(len(data), 0)
        self.assertEqual(data[0]["department_name"], "Phòng Hành chính quản trị")

    def test_get_departments_list(self):
        # Khởi tạo trước
        self.client.post("/api/v1/departments/init-standard/III")
        
        response = self.client.get("/api/v1/departments")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()), 0)
