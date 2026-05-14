"""
Router: Kho thuốc & Đơn thuốc
================================
Prefix  : /api/v1
Tags    : 7. System - Inventory & Audit

Luồng kê đơn thuốc:
  1. POST /prescriptions        — bác sĩ kê đơn → tự động trừ tồn kho (FEFO)
  2. POST /prescriptions/{id}/sign — ký số đơn thuốc
  3. GET  /prescriptions/{id}   — bệnh nhân xem đơn thuốc của mình

Luồng quản lý kho:
  1. POST /medications          — thêm thuốc vào danh mục
  2. POST /inventory            — nhập lô hàng mới
  3. GET  /inventory/expiring   — xem thuốc sắp hết hạn
  4. PATCH /inventory/{id}/adjust — điều chỉnh tồn kho thủ công
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.inventory import (
    MedicationCreate, MedicationUpdate, MedicationResponse,
    InventoryCreate, InventoryAdjust, InventoryResponse,
    PrescriptionCreate, PrescriptionSign, PrescriptionResponse,
)
from app.services import inventory_service as svc
from app.services.inventory_service import deactivate_medication, reactivate_medication
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="", tags=["7. System - Inventory & Audit"])


# ─────────────────────────────────────────────────────────────
# DANH MỤC THUỐC (MEDICATION)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/medications",
    response_model=List[MedicationResponse],
    summary="Xem danh sách thuốc trong hệ thống",
)
def list_medications(
    active_only: bool    = Query(False, description="True = chỉ hiển thị thuốc đang lưu hành"),
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Xem danh mục tất cả thuốc trong hệ thống.**

    - **active_only=false** *(mặc định)*: hiển thị cả thuốc đã ngừng lưu hành
    - **active_only=true**: chỉ hiển thị thuốc đang hoạt động — dùng khi kê đơn

    Mọi người dùng đã đăng nhập đều có thể xem danh mục thuốc để tham khảo.
    """
    return svc.list_medications(db, active_only)


@router.post(
    "/medications",
    response_model=MedicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Thêm thuốc mới vào danh mục",
)
def create_medication(
    payload    : MedicationCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Thêm thuốc mới vào danh mục hệ thống.

    - **med_code**: mã thuốc nội bộ (duy nhất, VD: `AMOX500`)
    - **med_name**: tên thuốc đầy đủ (VD: `Amoxicillin 500mg`)
    - **active_ingredient**: hoạt chất chính
    - **unit**: đơn vị tính (`viên`, `ml`, `lọ`...)
    - **price**: giá bán lẻ một đơn vị (VNĐ)
    - **is_bhyt_covered**: có nằm trong danh mục BHYT không
    """
    return svc.create_medication(db, payload)


@router.patch(
    "/medications/{medication_id}",
    response_model=MedicationResponse,
    summary="[ADMIN] Cập nhật thông tin thuốc",
)
def update_medication(
    medication_id: UUID,
    payload      : MedicationUpdate,
    db           : Session = Depends(get_db),
    current_acc  : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Sửa thông tin thuốc (giá, tên, trạng thái...).

    Chỉ truyền các trường cần thay đổi.

    **Ví dụ cập nhật giá:**
    ```json
    { "price": 15000 }
    ```
    """
    return svc.update_medication(db, medication_id, payload)


@router.delete(
    "/medications/{medication_id}",
    response_model=MedicationResponse,
    summary="[ADMIN] Ngừng lưu hành thuốc (soft delete — set is_active=False)",
)
def deactivate_med(
    medication_id: UUID,
    db           : Session = Depends(get_db),
    current_acc  : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Đánh dấu thuốc ngừng lưu hành.

    Thuốc sẽ không còn xuất hiện khi kê đơn hoặc đặt mua, nhưng lịch sử
    các đơn thuốc cũ vẫn được giữ nguyên (dữ liệu không bị xóa).

    Để khôi phục, dùng `PATCH /medications/{id}/reactivate`.
    """
    return deactivate_medication(db, medication_id)


@router.patch(
    "/medications/{medication_id}/reactivate",
    response_model=MedicationResponse,
    summary="[ADMIN] Khôi phục thuốc đã ngừng lưu hành",
)
def reactivate_med(
    medication_id: UUID,
    db           : Session = Depends(get_db),
    current_acc  : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Đưa thuốc đã ngừng lưu hành trở lại hoạt động.

    Sau khi khôi phục, thuốc có thể được kê đơn và đặt mua lại bình thường.
    """
    return reactivate_medication(db, medication_id)


# ─────────────────────────────────────────────────────────────
# KHO THUỐC (INVENTORY)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/inventory",
    response_model=List[InventoryResponse],
    summary="[ADMIN] Xem toàn bộ lô hàng trong kho",
)
def list_inventory(
    medication_id: Optional[UUID] = Query(None, description="Lọc theo thuốc cụ thể"),
    db           : Session        = Depends(get_db),
    current_acc  : Account        = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Liệt kê tất cả lô thuốc trong kho, kèm số lượng và ngày hết hạn.

    - **medication_id** *(tùy chọn)*: xem tất cả lô của một loại thuốc cụ thể

    Kết quả sắp xếp theo ngày hết hạn gần nhất trước — ưu tiên xuất lô cũ trước (FEFO).
    """
    return svc.list_inventory(db, medication_id)


@router.get(
    "/inventory/expiring",
    response_model=List[InventoryResponse],
    summary="[ADMIN] Xem thuốc sắp hết hạn",
)
def expiring_soon(
    days       : int     = Query(30, ge=1, description="Số ngày tới để kiểm tra (mặc định 30 ngày)"),
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Xem các lô thuốc sẽ hết hạn trong N ngày tới.

    - **days=30** *(mặc định)*: thuốc hết hạn trong 30 ngày tới
    - **days=7**: kiểm tra khẩn cấp (thuốc hết hạn trong tuần tới)

    Dùng để lên kế hoạch thanh lý hoặc đặt hàng bổ sung kịp thời.
    """
    return svc.get_expiring_soon(db, days)


@router.get(
    "/medications/{medication_id}/stock",
    summary="[ADMIN] Xem tổng tồn kho của một loại thuốc",
)
def stock_total(
    medication_id: UUID,
    db           : Session = Depends(get_db),
    current_acc  : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Xem tổng số lượng tồn kho còn lại của một loại thuốc.

    Chỉ tính các lô thuốc còn hạn sử dụng và thuốc đang hoạt động.

    **Trả về:**
    ```json
    { "medication_id": "...", "total_stock": 250 }
    ```
    """
    return {"medication_id": medication_id, "total_stock": svc.get_stock_total(db, medication_id)}


@router.post(
    "/inventory",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Nhập lô thuốc mới vào kho",
)
def add_batch(
    payload    : InventoryCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Nhập một lô thuốc mới vào kho.

    - **medication_id**: UUID loại thuốc cần nhập
    - **batch_number**: số lô (từ nhà sản xuất, VD: `LOT2026001`)
    - **quantity**: số lượng nhập (đơn vị theo `medication.unit`)
    - **expiration_date**: ngày hết hạn của lô (`YYYY-MM-DD`) — không được nhập lô đã hết hạn

    Mỗi lô có số lượng và ngày hết hạn riêng biệt.
    Khi kê đơn, hệ thống tự động xuất theo FEFO (First Expired, First Out).
    """
    return svc.add_inventory_batch(db, payload)


@router.patch(
    "/inventory/{inventory_id}/adjust",
    response_model=InventoryResponse,
    summary="[ADMIN] Điều chỉnh tồn kho thủ công (+/-)",
)
def adjust(
    inventory_id: UUID,
    payload     : InventoryAdjust,
    db          : Session = Depends(get_db),
    current_acc : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Điều chỉnh số lượng tồn kho thủ công — dùng khi kiểm kê.

    - **delta**: số lượng thay đổi
      - Số dương (+): nhập thêm (VD: `+10` khi tìm thấy hàng thừa)
      - Số âm (-): giảm bớt (VD: `-5` khi phát hiện hàng bị hỏng, mất mát)

    ⚠️ Không được giảm xuống dưới 0 — hệ thống sẽ từ chối.

    **Ví dụ giảm 5 đơn vị:**
    ```json
    { "delta": -5, "reason": "Phát hiện 5 lọ bị vỡ khi kiểm kê" }
    ```
    """
    return svc.adjust_inventory(db, inventory_id, payload)


# ─────────────────────────────────────────────────────────────
# ĐƠN THUỐC (PRESCRIPTION)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/prescriptions",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Kê đơn thuốc — tự động trừ tồn kho theo FEFO",
)
def create_prescription(
    payload    : PrescriptionCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Bác sĩ kê đơn thuốc cho bệnh nhân sau khi khám.

    Bắt buộc phải có `record_id` (bệnh án của lần khám đó).

    - **record_id**: UUID bệnh án tương ứng
    - **doctor_id**: UUID bác sĩ kê đơn
    - **items**: danh sách thuốc
      - `medication_id`: UUID loại thuốc
      - `quantity`: số lượng cần dùng
      - `dosage_instruction`: hướng dẫn dùng thuốc (VD: "Uống 2 viên/ngày sau ăn, dùng 5 ngày")

    **Hệ thống tự động:**
    1. Kiểm tra thuốc đang hoạt động và đủ tồn kho
    2. Trừ tồn kho theo nguyên tắc **FEFO** (lô gần hết hạn nhất xuất trước)
    3. Mỗi bệnh án chỉ được kê 1 đơn thuốc

    Sau khi tạo, cần ký số đơn thuốc qua `POST /prescriptions/{id}/sign`.
    """
    return svc.create_prescription(db, payload)


@router.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse,
    summary="Xem chi tiết đơn thuốc",
)
def get_prescription(
    prescription_id: UUID,
    db             : Session = Depends(get_db),
    current_acc    : Account = Depends(get_current_account),
):
    """
    **Xem đầy đủ thông tin đơn thuốc kèm danh sách thuốc và hướng dẫn dùng.**

    Response bao gồm:
    - Bác sĩ kê đơn
    - Danh sách thuốc với số lượng và hướng dẫn dùng
    - Trạng thái ký số (đã ký / chưa ký)

    Bệnh nhân chỉ xem được đơn thuốc của cuộc hẹn của mình.
    """
    rx = svc.get_prescription(db, prescription_id)
    if current_acc.role == "PATIENT":
        owner_id = rx.record.appointment.patient_id
        if owner_id != current_acc.account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return rx


@router.post(
    "/prescriptions/{prescription_id}/sign",
    response_model=PrescriptionResponse,
    summary="[ADMIN] Ký số đơn thuốc bằng hash chữ ký",
)
def sign_prescription(
    prescription_id: UUID,
    payload        : PrescriptionSign,
    db             : Session = Depends(get_db),
    current_acc    : Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Bác sĩ ký xác nhận đơn thuốc bằng chữ ký số.

    - **doctor_signature_hash**: chuỗi hash SHA-256 của chữ ký số bác sĩ

    Sau khi ký, đơn thuốc được khóa — không thể chỉnh sửa thêm.
    Hệ thống gửi thông báo đến bệnh nhân: *"Đơn thuốc đã được ký, có thể lấy thuốc tại quầy"*.

    Mỗi đơn thuốc chỉ được ký 1 lần.
    """
    return svc.sign_prescription(db, prescription_id, payload)
