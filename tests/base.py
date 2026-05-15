import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.config import settings

# Sử dụng SQLite in-memory để test cho nhanh và không cần cài đặt phức tạp
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            SQLALCHEMY_DATABASE_URL, 
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )

    def setUp(self):
        # Tạo bảng cho mỗi test để đảm bảo sạch sẽ
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

    def tearDown(self):
        self.db.close()
        # Xóa bảng sau mỗi test
        Base.metadata.drop_all(bind=self.engine)
