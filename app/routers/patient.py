"""
Router: Bệnh nhân & Thẻ BHYT
==============================
Prefix  : /api/v1
Tags    : 3. Patient - Profiles & BHYT

Phân quyền:
  - PATIENT : chỉ xem/sửa hồ sơ của chính mình
  - ADMIN   : toàn quyền trên tất cả bệnh nhân

Luồng khuyến nghị sau đăng ký:
  1. POST /patients/me/profile       — tạo hồ sơ đầy đủ
  2. POST /bhyt                      — thêm thẻ BHYT
  3. PATCH /bhyt/{id}/verify         — Admin xác minh thẻ
  4. GET  /patients/{id}/bhyt/active — kiểm tra thẻ đã sẵn sàng chưa
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status, Request, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.patient import (
    PatientCreate, PatientUpdate,
    PatientResponse, PatientWithBHYT, PatientProfileResponse,
    BHYTCreate, BHYTUpdate, BHYTVerifyUpdate, BHYTResponse,
    ConsentCreate, ConsentResponse,
)
from app.services import patient_service
from app.security import get_current_account, require_roles
from app.models.account import Account
from app.models.patient import Patient

router = APIRouter(prefix="", tags=["3. Patient - Profiles & BHYT"])


# ─────────────────────────────────────────────────────────────
# HỒ SƠ BỆNH NHÂN — TỰ QUẢN LÝ (/me)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/patients/me/profile",
    response_model=PatientProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo hồ sơ bệnh nhân lần đầu (sau khi đăng ký tài khoản)",
)
def create_my_profile(
    payload: PatientCreate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("PATIENT")),
):
    """
    **Bệnh nhân tự hoàn thiện hồ sơ sau khi đăng ký.**

    Bắt buộc thực hiện **trước khi đặt lịch khám**.
    Hồ sơ được liên kết trực tiếp với tài khoản (`patient_id` = `account_id`).

    **Trường bắt buộc:**
    - **first_name**: tên (VD: "Văn A")
    - **last_name**: họ (VD: "Nguyễn")
    - **dob**: ngày sinh định dạng `YYYY-MM-DD` (phải trong quá khứ)
    - **gender**: `MALE` / `FEMALE` / `OTHER`

    **Trường tùy chọn:** `phone`, `cccd`, `address`

    **Lưu ý:** SĐT và CCCD trong response sẽ được che bớt (***) vì lý do bảo mật.
    Mỗi tài khoản chỉ tạo hồ sơ được 1 lần. Dùng `PATCH /patients/me/profile` để cập nhật.
    """
    existing = db.query(Patient).filter(Patient.patient_id == current_acc.account_id).first()
    if existing and existing.first_name and existing.last_name:
        raise HTTPException(status_code=400, detail="Hồ sơ đã tồn tại. Dùng PATCH /patients/me/profile để cập nhật.")
    return patient_service.create_patient(db, payload, patient_id=current_acc.account_id)


@router.get(
    "/patients/me/profile",
    response_model=PatientProfileResponse,
    summary="Xem hồ sơ bệnh nhân của bản thân (có che thông tin nhạy cảm)",
)
def get_my_profile(
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("PATIENT")),
):
    """
    **Bệnh nhân xem thông tin hồ sơ của chính mình.**

    SĐT và CCCD sẽ được hiển thị dạng che: `090****678`, `012345******`.
    Để xem đầy đủ, Admin dùng `GET /patients/{patient_id}`.
    """
    return patient_service.get_patient_by_id(db, current_acc.account_id)


@router.patch(
    "/patients/me/profile",
    response_model=PatientProfileResponse,
    summary="Cập nhật hồ sơ bệnh nhân của bản thân",
)
def update_my_profile(
    payload: PatientUpdate,
    db: Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("PATIENT")),
):
    """
    **Bệnh nhân tự cập nhật thông tin cá nhân.**

    Chỉ truyền các trường cần thay đổi — không truyền trường nào thì giữ nguyên.

    **Ví dụ cập nhật địa chỉ:**
    ```json
    { "address": "123 Lê Lợi, Q1, TP.HCM" }
    ```

    **Không thể thay đổi:** `patient_id`, `created_at`.
    """
    return patient_service.update_patient(db, current_acc.account_id, payload)


# ─────────────────────────────────────────────────────────────
# QUẢN LÝ BỆNH NHÂN — ADMIN
# ─────────────────────────────────────────────────────────────

@router.get(
    "/patients",
    response_model=List[PatientResponse],
    summary="[ADMIN] Danh sách bệnh nhân (tìm kiếm theo tên / SĐT)",
)
def list_patients(
    skip   : int           = Query(0,   ge=0, description="Bỏ qua N bản ghi đầu"),
    limit  : int           = Query(20,  ge=1, le=100, description="Số lượng tối đa trả về"),
    search : Optional[str] = Query(None, description="Tìm kiếm theo họ tên hoặc số điện thoại"),
    db     : Session       = Depends(get_db),
    current_acc: Account   = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Lấy danh sách bệnh nhân, hỗ trợ phân trang và tìm kiếm.

    - **search**: tìm theo họ, tên hoặc số điện thoại (không phân biệt hoa thường)
    - **skip/limit**: phân trang — ví dụ `skip=20&limit=20` để lấy trang 2

    Response trả về thông tin đầy đủ (không che SĐT/CCCD) vì đây là giao diện nội bộ.
    """
    return patient_service.get_patients(db, skip, limit, search)


@router.get(
    "/patients/{patient_id}",
    response_model=PatientWithBHYT,
    summary="Xem chi tiết bệnh nhân kèm lịch sử BHYT",
)
def get_patient(
    patient_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Xem thông tin đầy đủ của một bệnh nhân kèm toàn bộ lịch sử thẻ BHYT.**

    - **PATIENT**: chỉ xem được hồ sơ của chính mình
    - **ADMIN**: xem được hồ sơ của bất kỳ bệnh nhân nào

    Response bao gồm: thông tin cá nhân + danh sách tất cả thẻ BHYT đã đăng ký.
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập: chỉ được xem hồ sơ của chính mình")
    return patient_service.get_patient_by_id(db, patient_id)


@router.post(
    "/patients",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Tạo hồ sơ bệnh nhân thủ công",
)
def create_patient(
    payload    : PatientCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Tạo hồ sơ bệnh nhân không gắn với tài khoản đăng nhập.

    Dùng khi Admin nhập dữ liệu bệnh nhân từ hệ thống cũ hoặc tạo hồ sơ giấy tờ.
    Để tạo bệnh nhân có tài khoản đăng nhập, dùng `POST /auth/accounts` với role `PATIENT`.
    """
    return patient_service.create_patient(db, payload)


@router.patch(
    "/patients/{patient_id}",
    response_model=PatientResponse,
    summary="Cập nhật thông tin bệnh nhân",
)
def update_patient(
    patient_id : UUID,
    payload    : PatientUpdate,
    db         : Session       = Depends(get_db),
    current_acc: Account       = Depends(get_current_account),
):
    """
    **Cập nhật thông tin hồ sơ bệnh nhân.**

    - **PATIENT**: chỉ cập nhật được hồ sơ của chính mình → dùng `PATCH /patients/me/profile`
    - **ADMIN**: cập nhật bất kỳ bệnh nhân nào

    Validation: SĐT và CCCD không được trùng với bệnh nhân khác. Ngày sinh phải trong quá khứ.
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập: chỉ được sửa hồ sơ của chính mình")
    return patient_service.update_patient(db, patient_id, payload)


@router.delete(
    "/patients/{patient_id}",
    status_code=status.HTTP_200_OK,
    summary="[ADMIN] Xóa hồ sơ bệnh nhân (hard delete)",
)
def delete_patient(
    patient_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Xóa vĩnh viễn hồ sơ bệnh nhân khỏi hệ thống.

    ⚠️ **Cảnh báo:** Thao tác này không thể hoàn tác.
    Nếu bệnh nhân có lịch sử cuộc hẹn, hóa đơn hoặc bệnh án, hệ thống sẽ từ chối xóa
    và trả về lỗi **409 Conflict** để bảo vệ tính toàn vẹn dữ liệu.
    """
    return patient_service.delete_patient(db, patient_id)


# ─────────────────────────────────────────────────────────────
# THẺ BẢO HIỂM Y TẾ (BHYT)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/patients/{patient_id}/bhyt",
    response_model=List[BHYTResponse],
    summary="Xem toàn bộ lịch sử thẻ BHYT của bệnh nhân",
)
def list_bhyt(
    patient_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Lấy tất cả thẻ BHYT từng đăng ký** (kể cả thẻ cũ đã hết hạn hoặc bị vô hiệu hóa).

    Trả về danh sách sắp xếp theo `valid_to` mới nhất trước.
    Để chỉ lấy thẻ đang hoạt động và hợp lệ, dùng `GET /patients/{id}/bhyt/active`.
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return patient_service.get_bhyt_by_patient(db, patient_id)


@router.get(
    "/patients/{patient_id}/bhyt/active",
    response_model=BHYTResponse,
    summary="Xem thẻ BHYT đang hoạt động và đã được xác minh",
    responses={
        200: {"description": "Thẻ hợp lệ — đang hoạt động, đã VERIFIED, còn hạn hôm nay"},
        404: {"description": "Không có thẻ / chưa xác minh / hết hạn — thông báo lỗi giải thích cụ thể lý do"},
    },
)
def get_active_bhyt(
    patient_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Trả về thẻ BHYT duy nhất đang có hiệu lực.**

    Thẻ được coi là hợp lệ khi thỏa đồng thời:
    - `is_active = True` (chưa bị vô hiệu hóa)
    - `check_status = VERIFIED` (Admin đã xác minh)
    - `valid_from <= hôm nay <= valid_to`

    **Nếu trả về 404**, đọc `detail` để biết lý do chính xác:
    - *"chưa được xác minh"* → Admin cần `PATCH /bhyt/{id}/verify`
    - *"đã hết hạn"* → bệnh nhân cần gia hạn qua `POST /orders/`
    - *"chưa có thẻ"* → cần `POST /bhyt` trước

    Endpoint này được hệ thống đặt lịch khám gọi tự động để kiểm tra bảo hiểm.
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return patient_service.get_active_bhyt(db, patient_id)


@router.get(
    "/patients/{patient_id}/bhyt/latest",
    response_model=Optional[BHYTResponse],
    summary="[Debug] Xem thẻ BHYT mới nhất bất kể trạng thái",
)
def get_latest_bhyt(
    patient_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Công cụ debug — xem thẻ BHYT mới nhất bất kể đã VERIFIED hay chưa.**

    Dùng khi `/bhyt/active` trả về 404 và cần kiểm tra trạng thái thực tế của thẻ:
    - Xem `check_status` hiện tại là gì (`PENDING` / `VERIFIED` / `REJECTED`)
    - Xem `bhyt_id` để gọi `PATCH /bhyt/{id}/verify`
    - Xem ngày hết hạn `valid_to`
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return patient_service.get_latest_bhyt(db, patient_id)


@router.post(
    "/bhyt",
    response_model=BHYTResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm thẻ BHYT mới (tự động vô hiệu hóa thẻ cũ)",
)
def create_bhyt(
    payload    : BHYTCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Đăng ký thẻ BHYT mới cho bệnh nhân.**

    Khi thêm thẻ mới, thẻ cũ sẽ tự động bị vô hiệu hóa (`is_active=False`).

    **Trường bắt buộc:**
    - **patient_id**: UUID của bệnh nhân
    - **bhyt_code**: mã thẻ BHYT 15 ký tự (VD: `DN1234567890xxx`)
    - **registered_hospital_code**: mã cơ sở đăng ký KCB ban đầu (VD: `01001`)
    - **valid_from / valid_to**: ngày hiệu lực (định dạng `YYYY-MM-DD`)

    **Sau khi thêm:** Thẻ có `check_status = PENDING`.
    Admin cần xác minh bằng `PATCH /bhyt/{bhyt_id}/verify` trước khi bệnh nhân dùng được.

    ⚠️ Bệnh nhân chỉ được thêm thẻ BHYT cho chính mình.
    """
    if current_acc.role == "PATIENT" and payload.patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không được thêm thẻ BHYT cho bệnh nhân khác")
    return patient_service.create_bhyt(db, payload)


@router.patch(
    "/bhyt/{bhyt_id}",
    response_model=BHYTResponse,
    summary="[ADMIN] Cập nhật thông tin thẻ BHYT (ngày, bệnh viện đăng ký...)",
)
def update_bhyt(
    bhyt_id    : UUID,
    payload    : BHYTUpdate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Sửa thông tin thẻ BHYT như ngày hết hạn, bệnh viện đăng ký...

    Chỉ ADMIN được phép sửa trực tiếp để tránh bệnh nhân tự sửa gian lận.
    Validation đảm bảo `valid_from <= valid_to` và không nhập ngày hết hạn đã qua.
    """
    return patient_service.update_bhyt(db, bhyt_id, payload)


@router.patch(
    "/bhyt/{bhyt_id}/verify",
    response_model=BHYTResponse,
    summary="[ADMIN] Xác minh hoặc từ chối thẻ BHYT",
)
def verify_bhyt(
    bhyt_id    : UUID,
    payload    : BHYTVerifyUpdate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Chỉ ADMIN]** Cập nhật kết quả xác minh thẻ BHYT với cổng BHXH.

    - **check_status**: `VERIFIED` (hợp lệ) / `PENDING` (đang chờ) / `REJECTED` (từ chối)

    Sau khi đặt thành `VERIFIED`, thẻ mới được sử dụng để:
    - Đặt lịch khám có bảo hiểm (`applied_bhyt_id` trong booking)
    - Tính tiền thanh toán sau khấu trừ BHYT
    - Kiểm tra qua `GET /patients/{id}/bhyt/active`

    **Thường quy trình là:**
    1. Bệnh nhân thêm thẻ → `check_status = PENDING`
    2. Admin/hệ thống đối chiếu với cổng BHXH Việt Nam
    3. Admin cập nhật → `check_status = VERIFIED`
    """
    return patient_service.verify_bhyt(db, bhyt_id, payload)


# ─────────────────────────────────────────────────────────────
# ĐỒNG Ý SỬ DỤNG DỮ LIỆU (CONSENT — chuẩn NĐ 13/2023)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/patients/{patient_id}/consents",
    response_model=List[ConsentResponse],
    summary="Xem lịch sử ký đồng ý của bệnh nhân",
)
def list_consents(
    patient_id : UUID,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Xem toàn bộ lịch sử đồng thuận** theo chuẩn Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân.

    Mỗi lần bệnh nhân đồng ý / rút đồng ý sẽ tạo một bản ghi mới (immutable audit trail).
    Không bao giờ xóa hay chỉnh sửa bản ghi cũ.
    """
    if current_acc.role == "PATIENT" and patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Từ chối truy cập")
    return patient_service.get_consents(db, patient_id)


@router.post(
    "/consents",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ghi nhận quyết định đồng ý / rút đồng ý sử dụng dữ liệu",
)
def record_consent(
    payload    : ConsentCreate,
    request    : Request,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Ghi nhận quyết định đồng thuận theo NĐ 13/2023.**

    Mỗi lần gọi tạo một bản ghi mới, không ghi đè bản ghi cũ.
    Hệ thống tự động ghi lại **IP address** và **User-Agent** từ request.

    - **patient_id**: bệnh nhân ký đồng ý
    - **consent_type**: loại đồng ý (VD: `DATA_PROCESSING`, `MARKETING`, `RESEARCH`)
    - **is_granted**: `true` = đồng ý, `false` = rút đồng ý

    ⚠️ Bệnh nhân không thể ký đồng thuận thay cho người khác.
    """
    if current_acc.role == "PATIENT" and payload.patient_id != current_acc.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không được ký đồng thuận thay cho bệnh nhân khác")
    if not payload.ip_address:
        payload.ip_address = request.client.host if request.client else None
    if not payload.user_agent:
        payload.user_agent = request.headers.get("user-agent")
    return patient_service.upsert_consent(db, payload)
