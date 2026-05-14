"""
Router: Bệnh án & Dịch vụ Lâm sàng
=====================================
Prefix  : /api/v1
Tags    : 6. Medical - Records & Results

Luồng ghi nhận bệnh án:
  1. Cuộc hẹn → IN_PROGRESS
  2. POST /medical-records          — tạo bệnh án (Admin/bác sĩ)
  3. PATCH /medical-records/{id}    — bổ sung thông tin (trước khi ký)
  4. PATCH /medical-records/{id}/sign — ký số bệnh án (khóa vĩnh viễn)
  5. POST /prescriptions            — kê đơn thuốc (nếu cần)
  6. PATCH /appointments/{id}/status → COMPLETED
"""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.medical_record import (
    MedicalRecordCreate, MedicalRecordUpdate, SignRecordRequest, MedicalRecordResponse,
    ClinicalServiceCreate, ClinicalServiceUpdate, ClinicalServiceResponse,
)
from app.services import medical_record_service as svc
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["6. Medical - Records & Results"])


# ─────────────────────────────────────────────────────────────
# DỊCH VỤ KHÁM CHỮA BỆNH (CLINICAL SERVICE)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/services",
    response_model=List[ClinicalServiceResponse],
    summary="Xem danh sách dịch vụ khám chữa bệnh (kèm bảng giá)",
)
def list_services(
    active_only: bool          = Query(True, description="True = chỉ hiển thị dịch vụ đang hoạt động"),
    bhyt_only  : bool          = Query(False, description="True = chỉ dịch vụ được BHYT thanh toán"),
    search     : str           = Query(None, description="Tìm kiếm theo tên hoặc mã dịch vụ"),
    db         : Session       = Depends(get_db),
):
    """
    **Xem bảng giá dịch vụ khám chữa bệnh.** (Không yêu cầu đăng nhập)

    - **active_only=true** *(mặc định)*: chỉ hiển thị dịch vụ đang hoạt động
    - **bhyt_only=true**: lọc những dịch vụ có trong danh mục thanh toán BHYT
    - **search**: tìm theo tên dịch vụ (VD: "Xét nghiệm", "Siêu âm")

    Bệnh nhân dùng endpoint này để xem bảng giá trước khi đặt lịch.
    """
    return svc.list_services(db, active_only, bhyt_only, search)


@router.get(
    "/services/{service_id}",
    response_model=ClinicalServiceResponse,
    summary="Xem chi tiết một dịch vụ theo ID",
)
def get_service(
    service_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Xem thông tin chi tiết của một dịch vụ khám chữa bệnh.**

    Bao gồm: tên dịch vụ, mã dịch vụ, giá, có BHYT thanh toán không, trạng thái hoạt động.
    """
    return svc.get_service(db, service_id)


@router.post(
    "/services",
    response_model=ClinicalServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Thêm dịch vụ khám chữa bệnh mới",
)
def create_service(
    payload    : ClinicalServiceCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Thêm dịch vụ khám chữa bệnh vào danh mục.

    - **service_code**: mã dịch vụ nội bộ (duy nhất, VD: `SV001`)
    - **service_name**: tên dịch vụ (VD: "Siêu âm ổ bụng tổng quát")
    - **price**: giá dịch vụ (VNĐ)
    - **is_bhyt_covered**: có được BHYT thanh toán không

    Dịch vụ mới tạo ra mặc định ở trạng thái `is_active=True`.
    """
    return svc.create_service(db, payload)


@router.patch(
    "/services/{service_id}",
    response_model=ClinicalServiceResponse,
    summary="[ADMIN] Cập nhật thông tin dịch vụ (tên, giá...)",
)
def update_service(
    service_id : UUID,
    payload    : ClinicalServiceUpdate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Cập nhật thông tin dịch vụ khám chữa bệnh.

    Chỉ truyền các trường cần thay đổi.

    **Ví dụ cập nhật giá:**
    ```json
    { "price": 350000 }
    ```
    """
    return svc.update_service(db, service_id, payload)


@router.delete(
    "/services/{service_id}",
    response_model=ClinicalServiceResponse,
    summary="[ADMIN] Ngừng cung cấp dịch vụ (soft delete — set is_active=False)",
)
def deactivate_service(
    service_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Đánh dấu dịch vụ ngừng hoạt động.

    Dịch vụ sẽ không còn xuất hiện trong bảng giá và không thể chỉ định khi khám,
    nhưng dữ liệu lịch sử bệnh án vẫn giữ nguyên.

    Để khôi phục, dùng `PATCH /services/{id}/reactivate`.
    """
    return svc.deactivate_service(db, service_id)


@router.patch(
    "/services/{service_id}/reactivate",
    response_model=ClinicalServiceResponse,
    summary="[ADMIN] Khôi phục dịch vụ đã ngừng hoạt động",
)
def reactivate_service(
    service_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Đưa dịch vụ đã ngừng hoạt động trở lại hoạt động bình thường.
    """
    return svc.reactivate_service(db, service_id)


# ─────────────────────────────────────────────────────────────
# HỒ SƠ BỆNH ÁN (MEDICAL RECORD)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/medical-records/{record_id}",
    response_model=MedicalRecordResponse,
    summary="Xem bệnh án theo ID",
)
def get_record(
    record_id  : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Xem thông tin đầy đủ của một bệnh án.**

    Response bao gồm:
    - Chẩn đoán, triệu chứng, kế hoạch điều trị
    - Mã ICD-10 (nếu có)
    - Các dịch vụ đã thực hiện trong lần khám
    - Trạng thái ký số bác sĩ
    - Danh sách đơn thuốc liên quan

    Bệnh nhân chỉ xem được bệnh án của cuộc hẹn của chính mình.
    """
    record = svc.get_record(db, record_id)
    if current_acc.role == "PATIENT":
        if record.appointment.patient_id != current_acc.account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối: Đây không phải bệnh án của bạn")
    return record


@router.get(
    "/appointments/{appointment_id}/medical-record",
    response_model=MedicalRecordResponse,
    summary="Xem bệnh án theo ID cuộc hẹn",
)
def get_by_appointment(
    appointment_id: UUID,
    db            : Session = Depends(get_db),
    current_acc   : Account = Depends(get_current_account),
):
    """
    **Lấy bệnh án từ cuộc hẹn thay vì từ record_id.**

    Tiện dụng hơn `GET /medical-records/{id}` khi bạn chỉ có `appointment_id`.
    Bệnh nhân chỉ xem được bệnh án của cuộc hẹn của mình.
    """
    record = svc.get_record_by_appointment(db, appointment_id)
    if current_acc.role == "PATIENT":
        if record.appointment.patient_id != current_acc.account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối: Đây không phải bệnh án của bạn")
    return record


@router.get(
    "/patients/{patient_id}/medical-records",
    response_model=List[MedicalRecordResponse],
    summary="Xem toàn bộ lịch sử bệnh án của bệnh nhân",
)
def get_patient_records(
    patient_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Xem tất cả bệnh án của một bệnh nhân qua các lần khám.**

    Dùng để:
    - Bệnh nhân tra cứu lịch sử khám bệnh của mình
    - Bác sĩ/Admin xem hồ sơ y tế đầy đủ trước khi khám mới

    Kết quả bao gồm tất cả bệnh án đã tạo (kể cả chưa ký số).
    Bệnh nhân chỉ xem được lịch sử của chính mình.
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return svc.get_records_by_patient(db, patient_id)


@router.post(
    "/medical-records",
    response_model=MedicalRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Tạo bệnh án mới (cuộc hẹn phải ở trạng thái IN_PROGRESS)",
)
def create_record(
    payload    : MedicalRecordCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Bác sĩ ghi nhận kết quả khám và tạo bệnh án.

    Cuộc hẹn phải đang ở trạng thái `IN_PROGRESS`.
    Mỗi cuộc hẹn chỉ có đúng 1 bệnh án.

    - **appointment_id**: UUID cuộc hẹn đang diễn ra
    - **doctor_id**: UUID bác sĩ khám
    - **diagnosis**: chẩn đoán (bắt buộc)
    - **icd10_code** *(tùy chọn)*: mã bệnh theo ICD-10 (VD: `J06.9`)
    - **symptoms** *(tùy chọn)*: triệu chứng lâm sàng
    - **treatment_plan** *(tùy chọn)*: kế hoạch điều trị

    Sau khi tạo, có thể bổ sung thông tin qua `PATCH /medical-records/{id}`
    cho đến khi ký số bằng `PATCH /medical-records/{id}/sign`.
    """
    return svc.create_record(db, payload)


@router.patch(
    "/medical-records/{record_id}",
    response_model=MedicalRecordResponse,
    summary="[ADMIN] Cập nhật bệnh án (chỉ được phép trước khi ký số)",
)
def update_record(
    record_id  : UUID,
    payload    : MedicalRecordUpdate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Bổ sung hoặc sửa thông tin bệnh án.

    ⚠️ **Chỉ cho phép chỉnh sửa trước khi bệnh án được ký số.**
    Sau khi ký (`signed_at` không null), bệnh án bị khóa vĩnh viễn.

    **Ví dụ bổ sung mã ICD-10:**
    ```json
    { "icd10_code": "K29.7", "treatment_plan": "Dùng thuốc PPI trong 4 tuần" }
    ```
    """
    return svc.update_record(db, record_id, payload)


@router.patch(
    "/medical-records/{record_id}/sign",
    response_model=MedicalRecordResponse,
    summary="[ADMIN] Bác sĩ ký số xác nhận bệnh án",
)
def sign_record(
    record_id  : UUID,
    payload    : SignRecordRequest,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Bác sĩ ký số bệnh án — bệnh án được khóa vĩnh viễn sau khi ký.

    - **doctor_signature_hash**: chuỗi hash SHA-256 của chữ ký số bác sĩ

    Sau khi ký:
    - Bệnh án không thể chỉnh sửa thêm
    - Hệ thống ghi nhận thời điểm ký (`signed_at`)
    - Bệnh án có giá trị pháp lý đầy đủ

    Mỗi bệnh án chỉ được ký 1 lần.
    """
    return svc.sign_record(db, record_id, payload)
