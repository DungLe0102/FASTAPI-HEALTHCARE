import sys
from sqlalchemy.orm import Session
from app.db import engine, SessionLocal
from app.services import department_service
from app.models.account import Account
from app.models.department import Department, Room
from app.security import get_password_hash
import uuid

def setup():
    print("--- START SEEDING DATA ---")
    db = SessionLocal()
    try:
        # 1. ADMIN Account
        admin = db.query(Account).filter(Account.email == "admin@healthcare").first()
        if not admin:
            print("- Creating admin account...")
            admin = Account(
                email="admin@healthcare",
                password_hash=get_password_hash("1234"),
                full_name="Administrator",
                role="ADMIN",
                is_active=True,
                email_verified=True
            )
            db.add(admin)
            db.flush()

        # 2. Standard Departments
        print("- Initializing standard departments (Class I)...")
        depts = department_service.init_standard_departments(db, "I")
        print(f"  Initialized {len(depts)} departments.")

        # 3. Sample Rooms
        print("- Adding sample rooms...")
        noi_th = db.query(Department).filter(Department.department_code == "K_NOITH").first()
        if noi_th:
            for i in range(1, 4):
                room_num = f"N{i:02d}"
                exists = db.query(Room).filter(Room.department_id == noi_th.department_id, Room.room_number == room_num).first()
                if not exists:
                    db.add(Room(department_id=noi_th.department_id, room_number=room_num, room_type="CONSULTATION"))
        
        ngoai_th = db.query(Department).filter(Department.department_code == "K_NGOAITH").first()
        if ngoai_th:
            for i in range(1, 3):
                room_num = f"NG{i:02d}"
                exists = db.query(Room).filter(Room.department_id == ngoai_th.department_id, Room.room_number == room_num).first()
                if not exists:
                    db.add(Room(department_id=ngoai_th.department_id, room_number=room_num, room_type="CONSULTATION"))

        db.commit()
        print("--- SEEDING COMPLETE ---")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    setup()
