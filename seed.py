import sys
import uuid
import random
from datetime import datetime, timedelta, time, date

# Cấu hình in UTF-8 cho Windows console
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy.orm import Session
from app.db import Base, SessionLocal, engine
from app.models.department import Department, Room
from app.models.doctor import Doctor, DoctorSchedule
from app.models.patient import Patient, PatientBHYT, PatientConsent
from app.models.appointment import Appointment
from app.models.medical_record import MedicalRecord, ClinicalService, RecordService
from app.models.inventory import Medication, Inventory, Prescription, PrescriptionItem
from app.models.billing import Billing, PaymentTransaction, DoctorPayout
from app.models.notification import Notification, SupportRequest
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.order import Order
from app.security import get_password_hash

# Danh sách tên tiếng Việt mẫu
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM_NAM = ["Văn", "Hữu", "Đức", "Công", "Quang", "Minh", "Xuân", "Thanh", "Bảo", "Đình", "Nhật", "Thế"]
DEM_NU = ["Thị", "Ngọc", "Thu", "Phương", "Mỹ", "Thanh", "Bích", "Kiều", "Mai", "Quỳnh", "Thảo", "Trúc"]
TEN_NAM = ["An", "Bình", "Dũng", "Duy", "Hải", "Hiếu", "Hòa", "Huy", "Khang", "Khoa", "Kiên", "Lâm", "Long", "Minh", "Nam", "Nghĩa", "Phong", "Phúc", "Quân", "Quang", "Quốc", "Tâm", "Thái", "Thành", "Thắng", "Thịnh", "Trí", "Trung", "Tuấn", "Tùng", "Vinh", "Việt"]
TEN_NU = ["An", "Anh", "Châu", "Giang", "Hà", "Hân", "Hoa", "Hương", "Khánh", "Lan", "Linh", "Ly", "Mai", "Nhi", "Ngọc", "Nhung", "Oanh", "Phương", "Quyên", "Tâm", "Thảo", "Thi", "Thu", "Thủy", "Tiên", "Trang", "Uyên", "Vân", "Vy", "Yến"]

def generate_vietnamese_name(is_male=None):
    if is_male is None:
        is_male = random.choice([True, False])
    ho = random.choice(HO)
    if is_male:
        dem = random.choice(DEM_NAM)
        ten = random.choice(TEN_NAM)
    else:
        dem = random.choice(DEM_NU)
        ten = random.choice(TEN_NU)
    return f"{ho} {dem} {ten}"

def cleanup_data(db: Session):
    print("=== DỌN DẸP DỮ LIỆU CŨ ===")
    
    tables_to_delete = [
        AuditLog,
        SupportRequest,
        Notification,
        Order,
        PaymentTransaction,
        Billing,
        PrescriptionItem,
        Prescription,
        RecordService,
        MedicalRecord,
        Appointment,
        DoctorSchedule,
        DoctorPayout,
        Doctor,
        Room,
        Department,
        Inventory,
        Medication,
        ClinicalService,
        PatientBHYT,
        PatientConsent,
        Patient,
        Account
    ]
    
    for table in tables_to_delete:
        try:
            db.query(table).delete()
            db.commit()
            print(f"  [-] Đã dọn dẹp bảng: {table.__tablename__}")
        except Exception as e:
            db.rollback()
            print(f"  [!] Bỏ qua dọn dẹp bảng {table.__tablename__} (có thể bảng chưa được tạo): {e}")
    
    print("[✔] Hoàn thành dọn dẹp cơ sở dữ liệu!\n")

def seed_data():
    db = SessionLocal()
    try:
        # Tự động tạo các bảng nếu chưa tồn tại
        print("=== TỰ ĐỘNG KHỞI TẠO CÁC BẢNG NẾU CHƯA CÓ ===")
        Base.metadata.create_all(bind=engine)
        print("[✔] Khởi tạo bảng thành công!\n")

        # 1. Cleanup old data
        cleanup_data(db)

        print("=== BẮT ĐẦU SEED DỮ LIỆU CHUẨN ===")

        # 2. Tạo tài khoản khoản Admin và Patient kiểm thử
        admin_pass_hash = get_password_hash("changethis")
        admin_pass_hash_backup = get_password_hash("123456")
        patient_pass_hash = get_password_hash("changethis")
        
        # Admin 1
        admin1 = Account(
            account_id=uuid.uuid4(),
            email="admin@healthcare.local",
            full_name="Quản Trị Viên Hệ Thống",
            password_hash=admin_pass_hash,
            role="ADMIN",
            is_active=True,
            email_verified=True
        )
        db.add(admin1)
        
        # Admin 2 (trùng khớp với .env mặc định)
        admin2 = Account(
            account_id=uuid.uuid4(),
            email="admin@gmail.com",
            full_name="Quản Trị Viên Dự Phòng",
            password_hash=admin_pass_hash_backup,
            role="ADMIN",
            is_active=True,
            email_verified=True
        )
        db.add(admin2)

        # Patient 1
        patient1_acc = Account(
            account_id=uuid.uuid4(),
            email="patient@healthcare.local",
            full_name="Nguyễn Văn Bệnh Nhân",
            password_hash=patient_pass_hash,
            role="PATIENT",
            is_active=True,
            email_verified=True
        )
        db.add(patient1_acc)
        db.flush()

        patient1 = Patient(
            patient_id=patient1_acc.account_id,
            first_name="Văn Bệnh Nhân",
            last_name="Nguyễn",
            dob=date(1990, 5, 15),
            gender="MALE",
            phone="0912345678",
            cccd="012345678901",
            address="123 Đường Láng, Quận Đống Đa, Hà Nội"
        )
        db.add(patient1)
        db.flush()

        patient1_bhyt = PatientBHYT(
            bhyt_id=uuid.uuid4(),
            patient_id=patient1.patient_id,
            bhyt_code="DN1234567890",
            registered_hospital_code="01001",
            valid_from=date(2025, 1, 1),
            valid_to=date(2026, 12, 31),
            is_active=True,
            check_status="VERIFIED"
        )
        db.add(patient1_bhyt)

        patient1_consent = PatientConsent(
            consent_id=uuid.uuid4(),
            patient_id=patient1.patient_id,
            consent_type="DATA_PROCESSING",
            is_granted=True,
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )
        db.add(patient1_consent)

        # Patient 2
        patient2_acc = Account(
            account_id=uuid.uuid4(),
            email="patient@gmail.com",
            full_name="Trần Thị Khách Hàng",
            password_hash=patient_pass_hash,
            role="PATIENT",
            is_active=True,
            email_verified=True
        )
        db.add(patient2_acc)
        db.flush()

        patient2 = Patient(
            patient_id=patient2_acc.account_id,
            first_name="Thị Khách Hàng",
            last_name="Trần",
            dob=date(1995, 8, 20),
            gender="FEMALE",
            phone="0987654321",
            cccd="012345678902",
            address="456 Phố Huế, Quận Hai Bà Trưng, Hà Nội"
        )
        db.add(patient2)
        db.flush()

        patient2_bhyt = PatientBHYT(
            bhyt_id=uuid.uuid4(),
            patient_id=patient2.patient_id,
            bhyt_code="DN1234567891",
            registered_hospital_code="01002",
            valid_from=date(2025, 1, 1),
            valid_to=date(2026, 12, 31),
            is_active=True,
            check_status="VERIFIED"
        )
        db.add(patient2_bhyt)

        patient2_consent = PatientConsent(
            consent_id=uuid.uuid4(),
            patient_id=patient2.patient_id,
            consent_type="DATA_PROCESSING",
            is_granted=True,
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )
        db.add(patient2_consent)

        print("[+] Khởi tạo thành công tài khoản Admin và Patient kiểm thử.")

        # 3. Tạo Clinical Services (Danh mục dịch vụ kỹ thuật)
        services_list = [
            {"code": "CS_KHAM_NOI", "name": "Khám Nội Khoa", "price": 150000.0, "is_bhyt": True},
            {"code": "CS_KHAM_NGOAI", "name": "Khám Ngoại Khoa", "price": 150000.0, "is_bhyt": True},
            {"code": "CS_KHAM_NHI", "name": "Khám Nhi Khoa", "price": 150000.0, "is_bhyt": True},
            {"code": "CS_SIEU_AM", "name": "Siêu âm bụng tổng quát", "price": 200000.0, "is_bhyt": True},
            {"code": "CS_XET_NGHIEM_MAU", "name": "Xét nghiệm công thức máu", "price": 120000.0, "is_bhyt": True},
            {"code": "CS_XQUANG_PHOI", "name": "Chụp X-quang phổi thẳng", "price": 180000.0, "is_bhyt": True},
            {"code": "CS_NOI_SOI_DA_DAY", "name": "Nội soi dạ dày gây mê", "price": 1200000.0, "is_bhyt": False},
            {"code": "CS_CT_SCAN", "name": "Chụp CT Scanner sọ não", "price": 1500000.0, "is_bhyt": False},
        ]
        
        clinical_services = {}
        for s_item in services_list:
            cs = ClinicalService(
                service_id=uuid.uuid4(),
                service_code=s_item["code"],
                service_name=s_item["name"],
                price=s_item["price"],
                is_bhyt_covered=s_item["is_bhyt"],
                is_active=True
            )
            db.add(cs)
            clinical_services[s_item["code"]] = cs
        db.flush()
        print("[+] Tạo danh mục Dịch Vụ Khám Chữa Bệnh (Clinical Services) thành công.")

        # 4. Tạo Medication & Inventory (Danh mục thuốc & kho thuốc)
        meds_list = [
            {"code": "MED_PARA_500", "name": "Paracetamol 500mg", "ingredient": "Paracetamol", "unit": "Viên", "price": 1500.0, "is_bhyt": True},
            {"code": "MED_AMOX_500", "name": "Amoxicillin 500mg", "ingredient": "Amoxicillin", "unit": "Viên", "price": 3000.0, "is_bhyt": True},
            {"code": "MED_IBU_400", "name": "Ibuprofen 400mg", "ingredient": "Ibuprofen", "unit": "Viên", "price": 2500.0, "is_bhyt": False},
            {"code": "MED_CET_10", "name": "Cetirizine 10mg", "ingredient": "Cetirizine", "unit": "Viên", "price": 1200.0, "is_bhyt": True},
            {"code": "MED_DECOLGEN", "name": "Decolgen Forte", "ingredient": "Acetaminophen, Phenylephrine", "unit": "Viên", "price": 2000.0, "is_bhyt": False},
            {"code": "MED_AUGMENTIN_1G", "name": "Augmentin 1g", "ingredient": "Amoxicillin + Clavulanate", "unit": "Viên", "price": 18000.0, "is_bhyt": True},
        ]

        medications = {}
        for m_item in meds_list:
            med = Medication(
                medication_id=uuid.uuid4(),
                med_code=m_item["code"],
                med_name=m_item["name"],
                active_ingredient=m_item["ingredient"],
                unit=m_item["unit"],
                price=m_item["price"],
                is_bhyt_covered=m_item["is_bhyt"],
                is_active=True
            )
            db.add(med)
            db.flush()
            medications[m_item["code"]] = med

            # Thêm kho hàng (Inventory)
            inv = Inventory(
                inventory_id=uuid.uuid4(),
                medication_id=med.medication_id,
                batch_number="BATCH-2026-A",
                quantity=1000,
                expiration_date=date(2028, 12, 31)
            )
            db.add(inv)
        db.flush()
        print("[+] Tạo danh mục Thuốc & số lượng Kho Thuốc thành công.")

        # 5. Xếp lịch khám (Doctors, Departments, Rooms, Schedules)
        start_date = datetime(2026, 5, 25)
        end_date = datetime(2026, 6, 30)
        delta = end_date - start_date
        days = [start_date + timedelta(days=i) for i in range(delta.days + 1)]

        departments_data = [
            {"code": "K_NOI", "name": "Khoa Nội"},
            {"code": "K_NGOAI", "name": "Khoa Ngoại"},
            {"code": "K_NHI", "name": "Khoa Nhi"}
        ]

        shifts = [
            (time(8, 0), time(10, 0)),   # Ca 1
            (time(10, 0), time(12, 0)),  # Ca 2
            (time(13, 0), time(15, 0))   # Ca 3
        ]

        all_doctors = []
        all_schedules = []

        for dep_info in departments_data:
            department = Department(
                department_id=uuid.uuid4(),
                department_code=dep_info["code"],  # Bỏ suffix ngẫu nhiên để chuẩn hóa
                department_name=dep_info["name"],
                is_active=True
            )
            db.add(department)
            db.flush()
            print(f"\n[+] Tạo khoa: {department.department_name} (Code: {department.department_code})")

            # Tạo 3 phòng khám cho mỗi khoa
            for i in range(1, 4):
                room = Room(
                    room_id=uuid.uuid4(),
                    department_id=department.department_id,
                    room_number=f"P.{dep_info['name'].split()[1]} {i}",
                    room_type="CONSULTATION",
                    is_active=True
                )
                db.add(room)
                db.flush()
                print(f"  [-] Tạo phòng khám: {room.room_number}")

                # Tạo 3 bác sĩ cho mỗi phòng khám
                for doc_idx in range(3):
                    is_male = random.choice([True, False])
                    full_name = generate_vietnamese_name(is_male)
                    parts = full_name.split()
                    first_name = parts[-1]
                    last_name = " ".join(parts[:-1])

                    doctor = Doctor(
                        doctor_id=uuid.uuid4(),
                        department_id=department.department_id,
                        first_name=first_name,
                        last_name=last_name,
                        specialization=f"Chuyên khoa {dep_info['name'].split()[1]}",
                        is_active=True,
                        is_simulator=True,
                        hourly_consultation_fee=150000
                    )
                    db.add(doctor)
                    db.flush()
                    all_doctors.append(doctor)
                    print(f"    [*] Tạo bác sĩ: {full_name} (Ca: {shifts[doc_idx][0].strftime('%H:%M')} - {shifts[doc_idx][1].strftime('%H:%M')})")

                    # Lịch khám của bác sĩ này
                    doc_shift_start, doc_shift_end = shifts[doc_idx]
                    
                    for day in days:
                        start_time = datetime.combine(day.date(), doc_shift_start)
                        end_time = datetime.combine(day.date(), doc_shift_end)
                        
                        schedule = DoctorSchedule(
                            schedule_id=uuid.uuid4(),
                            doctor_id=doctor.doctor_id,
                            room_id=room.room_id,
                            start_time=start_time,
                            end_time=end_time,
                            max_patients=10,
                            current_booked=0,
                            status="AVAILABLE"
                        )
                        db.add(schedule)
                        all_schedules.append(schedule)
            db.flush()

        # 6. Seed mock completed/past appointments (Lịch sử khám bệnh)
        # Tạo 3 ca khám đã hoàn thành trong quá khứ (Ví dụ từ ngày 15/05 đến 24/05/2026)
        print("\n=== SEED LỊCH SỬ KHÁM BỆNH ĐÃ HOÀN THÀNH ===")
        past_dates = [datetime(2026, 5, 15), datetime(2026, 5, 18), datetime(2026, 5, 20)]
        patients = [patient1, patient2]
        
        for idx, p_item in enumerate(patients):
            for i, p_date in enumerate(past_dates):
                # Chọn bác sĩ không trùng lặp cho cùng một ngày để tránh uq_doctor_schedule
                doc = all_doctors[(idx * len(past_dates) + i) % len(all_doctors)]
                
                # Tạo một schedule giả lập trong quá khứ
                past_start = datetime.combine(p_date.date(), time(9, 0))
                past_end = datetime.combine(p_date.date(), time(11, 0))
                
                past_schedule = DoctorSchedule(
                    schedule_id=uuid.uuid4(),
                    doctor_id=doc.doctor_id,
                    room_id=db.query(Room).filter(Room.department_id == doc.department_id).first().room_id,
                    start_time=past_start,
                    end_time=past_end,
                    max_patients=10,
                    current_booked=1,
                    status="AVAILABLE"
                )
                db.add(past_schedule)
                db.flush()

                # Cuộc hẹn hoàn thành
                appt = Appointment(
                    appointment_id=uuid.uuid4(),
                    patient_id=p_item.patient_id,
                    doctor_id=doc.doctor_id,
                    schedule_id=past_schedule.schedule_id,
                    applied_bhyt_id=patient1_bhyt.bhyt_id if idx == 0 else patient2_bhyt.bhyt_id,
                    appointment_date=past_start,
                    status="COMPLETED",
                    created_at=past_start - timedelta(days=2)
                )
                db.add(appt)
                db.flush()

                # Tạo bệnh án (Medical Record)
                m_record = MedicalRecord(
                    record_id=uuid.uuid4(),
                    appointment_id=appt.appointment_id,
                    ma_lk=f"LK-{random.randint(100000, 999999)}",
                    icd10_code=random.choice(["J06.9", "K29.0", "M54.5"]),
                    diagnosis=random.choice(["Viêm họng cấp tính", "Viêm dạ dày nhẹ", "Đau lưng cơ năng"]),
                    symptoms="Ho khan, đau họng nhẹ, sốt nhẹ" if idx == 0 else "Đau âm ỉ vùng thượng vị, đầy hơi",
                    treatment_plan="Uống thuốc theo đơn, hạn chế đồ cay nóng và làm việc quá sức. Nghỉ ngơi.",
                    doctor_signature_hash=f"SHA256-{uuid.uuid4().hex[:32]}",
                    signed_at=past_start + timedelta(minutes=45),
                    created_at=past_start
                )
                db.add(m_record)
                db.flush()

                # Ghi nhận dịch vụ kỹ thuật (Record Service)
                # Dùng CS_KHAM_NOI / CS_KHAM_NGOAI / CS_KHAM_NHI tùy thuộc vào khoa của doctor
                dep_code = db.query(Department).filter(Department.department_id == doc.department_id).first().department_code
                serv_code = "CS_KHAM_NOI"
                if "NGOAI" in dep_code:
                    serv_code = "CS_KHAM_NGOAI"
                elif "NHI" in dep_code:
                    serv_code = "CS_KHAM_NHI"

                service_primary = clinical_services[serv_code]
                rs1 = RecordService(
                    record_service_id=uuid.uuid4(),
                    record_id=m_record.record_id,
                    service_id=service_primary.service_id,
                    quantity=1,
                    actual_price=service_primary.price
                )
                db.add(rs1)

                service_secondary = clinical_services["CS_SIEU_AM"]
                rs2 = RecordService(
                    record_service_id=uuid.uuid4(),
                    record_id=m_record.record_id,
                    service_id=service_secondary.service_id,
                    quantity=1,
                    actual_price=service_secondary.price
                )
                db.add(rs2)

                # Tạo Đơn Thuốc (Prescription)
                pres = Prescription(
                    prescription_id=uuid.uuid4(),
                    record_id=m_record.record_id,
                    doctor_id=doc.doctor_id,
                    notes="Uống sau ăn 30 phút. Uống nhiều nước ấm.",
                    doctor_signature_hash=f"SHA256-{uuid.uuid4().hex[:32]}",
                    signed_at=past_start + timedelta(minutes=45)
                )
                db.add(pres)
                db.flush()

                # Chi tiết đơn thuốc (Prescription Items)
                p_item1 = PrescriptionItem(
                    item_id=uuid.uuid4(),
                    prescription_id=pres.prescription_id,
                    medication_id=medications["MED_PARA_500"].medication_id,
                    quantity=10,
                    dosage_instruction="Uống 1 viên khi sốt > 38.5 độ, cách tối thiểu 4-6 tiếng."
                )
                db.add(p_item1)

                p_item2 = PrescriptionItem(
                    item_id=uuid.uuid4(),
                    prescription_id=pres.prescription_id,
                    medication_id=medications["MED_CET_10"].medication_id,
                    quantity=7,
                    dosage_instruction="Uống 1 viên vào buổi tối trước khi đi ngủ."
                )
                db.add(p_item2)

                # 7. Hóa đơn và Thanh toán (Billing & Payment Transaction)
                total_amt = 523400.0
                bhyt_amt = 298720.0
                patient_amt = total_amt - bhyt_amt

                billing = Billing(
                    billing_id=uuid.uuid4(),
                    appointment_id=appt.appointment_id,
                    total_amount=total_amt,
                    bhyt_covered_amount=bhyt_amt,
                    patient_paid_amount=patient_amt,
                    billing_status="PAID",
                    created_at=past_start - timedelta(minutes=30)
                )
                db.add(billing)
                db.flush()

                trans = PaymentTransaction(
                    transaction_id=uuid.uuid4(),
                    billing_id=billing.billing_id,
                    payment_method="VIETQR",
                    amount=patient_amt,
                    gateway_reference_id=f"FT{random.randint(100000000, 999999999)}",
                    transaction_status="SUCCESS",
                    payment_date=past_start - timedelta(minutes=15)
                )
                db.add(trans)
                print(f"  [-] Đã tạo hồ sơ khám lịch sử ngày {p_date.strftime('%Y-%m-%d')} cho {p_item.last_name} {p_item.first_name}")

        # 8. Seed simulated upcoming / testing states appointments
        # Ca 1: PENDING_PAYMENT (Bệnh nhân 1 vừa đặt lịch cách đây 2 phút, chờ thanh toán)
        print("\n=== SEED CUỘC HẸN CHỜ THANH TOÁN (PENDING_PAYMENT) ===")
        doc_active = all_doctors[0]
        # Tìm một schedule trống vào ngày mai (25/05/2026)
        tomorrow_sched = db.query(DoctorSchedule).filter(
            DoctorSchedule.doctor_id == doc_active.doctor_id,
            DoctorSchedule.start_time >= datetime(2026, 5, 25, 0, 0),
            DoctorSchedule.start_time <= datetime(2026, 5, 25, 23, 59)
        ).first()

        if tomorrow_sched:
            tomorrow_sched.current_booked += 1
            
            appt_pending = Appointment(
                appointment_id=uuid.uuid4(),
                patient_id=patient1.patient_id,
                doctor_id=doc_active.doctor_id,
                schedule_id=tomorrow_sched.schedule_id,
                applied_bhyt_id=patient1_bhyt.bhyt_id,
                appointment_date=tomorrow_sched.start_time,
                status="PENDING_PAYMENT",
                locked_until=datetime.now() + timedelta(minutes=10),
                created_at=datetime.now() - timedelta(minutes=2)
            )
            db.add(appt_pending)
            db.flush()

            billing_pending = Billing(
                billing_id=uuid.uuid4(),
                appointment_id=appt_pending.appointment_id,
                total_amount=300000.0,
                bhyt_covered_amount=240000.0,
                patient_paid_amount=60000.0,
                billing_status="UNPAID",
                created_at=datetime.now() - timedelta(minutes=2)
            )
            db.add(billing_pending)
            
            # Tạo giao dịch PENDING
            trans_pending = PaymentTransaction(
                transaction_id=uuid.uuid4(),
                billing_id=billing_pending.billing_id,
                payment_method="VIETQR",
                amount=60000.0,
                gateway_reference_id=f"FT{random.randint(100000000, 999999999)}",
                transaction_status="PENDING",
                payment_date=None
            )
            db.add(trans_pending)
            print(f"  [✔] Đã tạo cuộc hẹn PENDING_PAYMENT thành công. ID Hóa Đơn: {billing_pending.billing_id}")

        # Ca 2: SCHEDULED (Bệnh nhân 2 đã đặt và thanh toán thành công cho ngày mai)
        print("\n=== SEED CUỘC HẸN ĐÃ XÁC NHẬN (SCHEDULED) ===")
        doc_active2 = all_doctors[1]
        tomorrow_sched2 = db.query(DoctorSchedule).filter(
            DoctorSchedule.doctor_id == doc_active2.doctor_id,
            DoctorSchedule.start_time >= datetime(2026, 5, 25, 0, 0),
            DoctorSchedule.start_time <= datetime(2026, 5, 25, 23, 59)
        ).first()

        if tomorrow_sched2:
            tomorrow_sched2.current_booked += 1
            
            appt_scheduled = Appointment(
                appointment_id=uuid.uuid4(),
                patient_id=patient2.patient_id,
                doctor_id=doc_active2.doctor_id,
                schedule_id=tomorrow_sched2.schedule_id,
                applied_bhyt_id=patient2_bhyt.bhyt_id,
                appointment_date=tomorrow_sched2.start_time,
                status="SCHEDULED",
                created_at=datetime.now() - timedelta(hours=1)
            )
            db.add(appt_scheduled)
            db.flush()

            billing_scheduled = Billing(
                billing_id=uuid.uuid4(),
                appointment_id=appt_scheduled.appointment_id,
                total_amount=300000.0,
                bhyt_covered_amount=240000.0,
                patient_paid_amount=60000.0,
                billing_status="PAID",
                created_at=datetime.now() - timedelta(hours=1)
            )
            db.add(billing_scheduled)
            
            trans_scheduled = PaymentTransaction(
                transaction_id=uuid.uuid4(),
                billing_id=billing_scheduled.billing_id,
                payment_method="VIETQR",
                amount=60000.0,
                gateway_reference_id=f"FT{random.randint(100000000, 999999999)}",
                transaction_status="SUCCESS",
                payment_date=datetime.now() - timedelta(minutes=55)
            )
            db.add(trans_scheduled)
            print(f"  [✔] Đã tạo cuộc hẹn SCHEDULED thành công.")

        # 9. Seed Doctor Payouts (Lương / Thù lao bác sĩ)
        print("\n=== SEED LỊCH SỬ THANH TOÁN BÁC SĨ (DOCTOR PAYOUTS) ===")
        payout1 = DoctorPayout(
            payout_id=uuid.uuid4(),
            doctor_id=all_doctors[0].doctor_id,
            amount=4500000.0,
            payout_date=date(2026, 5, 10),
            status="PAID",
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 10),
            notes="Quyết toán thù lao đợt 1 tháng 5"
        )
        db.add(payout1)

        payout2 = DoctorPayout(
            payout_id=uuid.uuid4(),
            doctor_id=all_doctors[1].doctor_id,
            amount=3200000.0,
            payout_date=date(2026, 5, 20),
            status="PENDING",
            period_start=date(2026, 5, 11),
            period_end=date(2026, 5, 20),
            notes="Quyết toán thù lao đợt 2 tháng 5"
        )
        db.add(payout2)
        print("[+] Seed thù lao thành công.")

        # 10. Seed Orders (Đơn hàng Gia Hạn BHYT & Mua Thuốc)
        print("\n=== SEED ĐƠN HÀNG (ORDERS) ===")
        # Đơn gia hạn BHYT thành công
        order_bhyt = Order(
            order_id=uuid.uuid4(),
            patient_id=patient1.patient_id,
            order_type="BHYT_EXTENSION",
            total_amount=450000.0,  # Ví dụ 6 tháng
            status="PAID",
            created_at=datetime.now() - timedelta(days=1),
            expires_at=datetime.now() - timedelta(days=1) + timedelta(minutes=10),
            order_metadata={
                "bhyt_id": str(patient1_bhyt.bhyt_id),
                "extension_months": 6,
                "bhyt_code": patient1_bhyt.bhyt_code
            }
        )
        db.add(order_bhyt)

        # Đơn hàng mua thuốc đang chờ xử lý
        order_med = Order(
            order_id=uuid.uuid4(),
            patient_id=patient1.patient_id,
            order_type="PHARMACY",
            total_amount=85000.0,
            status="PENDING",
            created_at=datetime.now() - timedelta(minutes=5),
            expires_at=datetime.now() + timedelta(minutes=5),
            order_metadata={
                "items": [
                    {"medication_id": str(medications["MED_PARA_500"].medication_id), "quantity": 10, "price": 1500.0, "deducted_batches": []},
                    {"medication_id": str(medications["MED_IBU_400"].medication_id), "quantity": 28, "price": 2500.0, "deducted_batches": []}
                ]
            }
        )
        db.add(order_med)
        print("[+] Seed đơn hàng thành công.")

        # 11. Seed Support Requests & Notifications
        print("\n=== SEED YÊU CẦU HỖ TRỢ & THÔNG BÁO ===")
        req1 = SupportRequest(
            request_id=uuid.uuid4(),
            patient_id=patient1.patient_id,
            request_type="BHYT_VERIFICATION",
            title="Đề nghị duyệt thẻ BHYT",
            content="Tôi đã gửi thẻ BHYT mới gia hạn qua VietQR, xin hãy cập nhật trạng thái.",
            assigned_to=admin1.account_id,
            priority="NORMAL",
            status="OPEN",
            created_at=datetime.now() - timedelta(hours=3)
        )
        db.add(req1)

        req2 = SupportRequest(
            request_id=uuid.uuid4(),
            patient_id=patient2.patient_id,
            request_type="PAYMENT_ERR",
            title="Thanh toán không cập nhật trạng thái",
            content="Tôi chuyển khoản thành công nhưng lịch hẹn vẫn báo chưa thanh toán. Xin xem xét.",
            assigned_to=admin1.account_id,
            priority="HIGH",
            status="RESOLVED",
            resolved_at=datetime.now() - timedelta(minutes=30),
            created_at=datetime.now() - timedelta(hours=4)
        )
        db.add(req2)

        notif1 = Notification(
            notification_id=uuid.uuid4(),
            recipient_id=patient1.patient_id,
            recipient_type="PATIENT",
            notification_type="APPOINTMENT_REMINDER",
            channel="EMAIL",
            title="Nhắc nhở lịch khám bệnh",
            content="Bạn có lịch hẹn khám với Bác sĩ ngày mai lúc 08:00. Vui lòng đến đúng giờ.",
            status="SENT",
            sent_at=datetime.now() - timedelta(hours=1),
            created_at=datetime.now() - timedelta(hours=1)
        )
        db.add(notif1)

        notif2 = Notification(
            notification_id=uuid.uuid4(),
            recipient_id=patient1.patient_id,
            recipient_type="PATIENT",
            notification_type="BILLING_SUCCESS",
            channel="EMAIL",
            title="Hóa đơn thanh toán thành công",
            content="Bạn đã thanh toán thành công 450,000đ cho đơn hàng gia hạn thẻ BHYT.",
            status="SENT",
            sent_at=datetime.now() - timedelta(days=1),
            created_at=datetime.now() - timedelta(days=1)
        )
        db.add(notif2)
        print("[+] Seed yêu cầu hỗ trợ và thông báo thành công.")

        db.commit()
        print("\n===========================================")
        print("[✔][✔][✔] SEED TOÀN BỘ DỮ LIỆU THÀNH CÔNG [✔][✔][✔]")
        print("Tài khoản kiểm thử Admin:")
        print("  - Email: admin@healthcare.local / Mật khẩu: changethis")
        print("  - Email: admin@gmail.com / Mật khẩu: 123456")
        print("Tài khoản kiểm thử Patient:")
        print("  - Email: patient@healthcare.local / Mật khẩu: changethis")
        print("  - Email: patient@gmail.com / Mật khẩu: changethis")
        print("===========================================")
    except Exception as e:
        db.rollback()
        print(f"\n[!] CÓ LỖI XẢY RA TRONG QUÁ TRÌNH SEED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
