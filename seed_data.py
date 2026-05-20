from app.db import SessionLocal
from app.models.department import Department, Room
from app.models.doctor import Doctor
import random

db = SessionLocal()

deps = db.query(Department).all()

print(f"Found {len(deps)} departments.")

first_names = ["An", "Bình", "Cường", "Dũng", "Em", "Hoa", "Giang", "Hải", "Linh", "Minh", "Ngọc", "Oanh", "Phương", "Quang", "Trang"]
last_names = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương"]

rooms_added = 0
docs_added = 0

for dep in deps:
    # 5 rooms
    for i in range(1, 6):
        r = Room(
            department_id=dep.department_id,
            room_number=f"{dep.department_code}-{i}01",
            room_type="KHAM_BENH"
        )
        db.add(r)
        rooms_added += 1
    
    # 25 doctors (5 per room)
    for i in range(25):
        d = Doctor(
            department_id=dep.department_id,
            first_name=random.choice(first_names),
            last_name=random.choice(last_names) + " " + random.choice(["Văn", "Thị", "Hữu", "Đức", "Ngọc", "Minh"]),
            specialization=f"Chuyên khoa {dep.department_name}",
            hourly_consultation_fee=random.choice([100000, 150000, 200000, 300000, 500000]),
            is_active=True,
            is_simulator=False
        )
        db.add(d)
        docs_added += 1

db.commit()
print(f"Seeding complete: {rooms_added} rooms and {docs_added} doctors added.")
