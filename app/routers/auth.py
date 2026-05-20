"""
Router: Xác thực & Quản lý tài khoản
======================================
Prefix  : /api/v1/auth
Tags    : 0. Authentication & Security

Luồng sử dụng:
  1. Bệnh nhân mới → POST /signup → POST /patients/me/profile
  2. Đăng nhập       → POST /login → nhận access_token
  3. Admin tạo tài khoản nội bộ → POST /accounts
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID
import jwt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.models.account import Account
from app.schemas.account import (
    AccountCreate, AccountUpdate, AccountResponse,
    Token, ChangePasswordRequest, UpdateMe,
    UserRegister, NewPassword, Message,
    ForgotPasswordRequest, VerifyResetOTPRequest, VerifyResetOTPResponse,
    RefreshRequest, ResendOTPRequest,
)
from app.security import (
    get_password_hash, hash_password, verify_password,
    create_access_token, get_current_active_superuser, CurrentAccount,
    create_refresh_token, ALGORITHM,
)
from app.config import settings
from app.utils import (
    generate_new_account_email, generate_password_reset_token,
    verify_password_reset_token, send_email,
    generate_otp, generate_reset_otp_email,
)

router = APIRouter(prefix="/auth", tags=["0. Authentication & Security"])


# ─────────────────────────────────────────────────────────────
# ĐĂNG NHẬP
# ─────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=Token,
    summary="Đăng nhập — nhận access token (email + mật khẩu)",
)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    **Đăng nhập hệ thống.**

    - **username**: địa chỉ email đã đăng ký
    - **password**: mật khẩu

    **Trả về:**
    - `access_token`: JWT token — dán vào ô Authorize ở đầu trang Swagger
    - `role`: vai trò của tài khoản (`ADMIN` / `PATIENT`)
    - `account_id`: UUID tài khoản (bệnh nhân cần dùng để gọi các API tiếp theo)

    **Lưu ý:** Token hết hạn sau `ACCESS_TOKEN_EXPIRE_MINUTES` phút (mặc định 60 phút).
    Khi hết hạn, hệ thống trả 401 — cần đăng nhập lại để lấy token mới.
    """
    account = db.query(Account).filter(Account.email == form.username).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sai email hoặc mật khẩu")

    is_valid, new_hash = verify_password(form.password, account.password_hash)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sai email hoặc mật khẩu")

    if not account.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đã bị vô hiệu hóa")

    # Tự động nâng cấp bcrypt → Argon2id khi đăng nhập
    if new_hash:
        account.password_hash = new_hash

    account.last_login = datetime.now()
    db.commit()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return Token(
        access_token=create_access_token(
            subject=str(account.account_id),
            expires_delta=access_token_expires,
            role=account.role,
        ),
        refresh_token=create_refresh_token(
            subject=str(account.account_id),
            expires_delta=refresh_token_expires,
        ),
        role=account.role,
        account_id=str(account.account_id),
    )


@router.post(
    "/refresh-token",
    response_model=Token,
    summary="Làm mới access token bằng refresh token",
)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        decoded = jwt.decode(payload.refresh_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        account_id = decoded.get("sub")
        if not account_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    
    try:
        subject_uuid = UUID(account_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid account format")

    account = db.query(Account).filter(Account.account_id == subject_uuid).first()
    if not account or not account.is_active:
        raise HTTPException(status_code=401, detail="Account not found or inactive")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    return Token(
        access_token=create_access_token(
            subject=str(account.account_id),
            expires_delta=access_token_expires,
            role=account.role,
        ),
        refresh_token=create_refresh_token(
            subject=str(account.account_id),
            expires_delta=refresh_token_expires,
        ),
        role=account.role,
        account_id=str(account.account_id),
    )


# ─────────────────────────────────────────────────────────────
# ĐĂNG KÝ (dành cho bệnh nhân tự đăng ký)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản bệnh nhân mới",
)
def signup(
    payload: UserRegister,
    db: Session = Depends(get_db),
):
    """
    **Bệnh nhân tự đăng ký tài khoản.** Role mặc định là `PATIENT`.

    - **email**: địa chỉ email hợp lệ, chưa từng đăng ký
    - **password**: mật khẩu tối thiểu 8 ký tự

    **Sau khi đăng ký thành công:**
    1. Đăng nhập qua `POST /auth/login` để lấy token
    2. Gọi `POST /patients/me/profile` để hoàn thiện hồ sơ cá nhân
       *(bắt buộc trước khi đặt lịch khám)*

    **Lưu ý:** Một hồ sơ Patient mặc định được tạo tự động cùng tài khoản.
    Bạn cần cập nhật thông tin thực tế qua `PATCH /patients/me/profile`.
    """
    existing = db.query(Account).filter(Account.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email này đã được đăng ký trong hệ thống")

    account = Account(
        email=payload.email,
        full_name=None,
        password_hash=get_password_hash(payload.password),
        role="PATIENT",
        email_verified=True,
    )
    db.add(account)
    db.flush()

    from datetime import date as date_cls
    from app.models.patient import Patient
    patient = Patient(
        patient_id=account.account_id,
        first_name="Patient",
        last_name=payload.email.split("@")[0],
        dob=date_cls(2000, 1, 1),
    )
    db.add(patient)
    db.commit()
    db.refresh(account)
    return account


# ─────────────────────────────────────────────────────────────
# THÔNG TIN TÀI KHOẢN ĐANG ĐĂNG NHẬP
# ─────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=AccountResponse,
    summary="Xem thông tin tài khoản đang đăng nhập",
)
def me(account: CurrentAccount):
    """
    **Trả về thông tin tài khoản của người đang đăng nhập.**

    Không cần truyền tham số — hệ thống tự đọc từ JWT token trong header.

    **Thường dùng để:**
    - Lấy `account_id` (= `patient_id` với bệnh nhân) để gọi các API khác
    - Kiểm tra `role` hiện tại
    - Xác nhận token còn hiệu lực
    """
    return account


@router.patch(
    "/me",
    response_model=AccountResponse,
    summary="Cập nhật thông tin cá nhân (email, họ tên)",
)
def update_me(
    payload: UpdateMe,
    account: CurrentAccount,
    db: Session = Depends(get_db),
):
    """
    **Người dùng tự cập nhật email hoặc tên hiển thị của mình.**

    - **email** *(tùy chọn)*: email mới — phải chưa được dùng bởi tài khoản khác
    - **full_name** *(tùy chọn)*: tên hiển thị

    **Lưu ý:** Đây là thông tin tài khoản, không phải hồ sơ bệnh nhân.
    Để cập nhật ngày sinh, số điện thoại... hãy dùng `PATCH /patients/me/profile`.
    """
    if payload.email and payload.email != account.email:
        existing = db.query(Account).filter(Account.email == payload.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email đã được dùng bởi tài khoản khác")
        account.email = payload.email
    if payload.full_name is not None:
        account.full_name = payload.full_name
    db.commit()
    db.refresh(account)
    return account


@router.patch(
    "/me/password",
    response_model=Message,
    summary="Đổi mật khẩu",
)
def change_password_me(
    payload: ChangePasswordRequest,
    account: CurrentAccount,
    db: Session = Depends(get_db),
):
    """
    **Người dùng tự đổi mật khẩu khi đang đăng nhập.**

    - **current_password**: mật khẩu hiện tại
    - **new_password**: mật khẩu mới (phải khác mật khẩu cũ, tối thiểu 8 ký tự)

    **Trường hợp quên mật khẩu:** Dùng `POST /auth/forgot-password` thay thế.
    """
    is_valid, _ = verify_password(payload.current_password, account.password_hash)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu hiện tại không đúng")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu mới phải khác mật khẩu cũ")
    account.password_hash = get_password_hash(payload.new_password)
    db.commit()
    return Message(message="Đổi mật khẩu thành công")


# ─────────────────────────────────────────────────────────────
# QUÊN MẬT KHẨU — RESET QUA OTP
# ─────────────────────────────────────────────────────────────

@router.post(
    "/forgot-password",
    response_model=Message,
    summary="Gửi OTP reset mật khẩu qua email",
)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    **Gửi mã OTP 6 chữ số đến email để reset mật khẩu.**

    - **email**: địa chỉ email đã đăng ký

    **Quy trình reset mật khẩu (3 bước):**
    1. `POST /auth/forgot-password` → nhận OTP qua email
    2. `POST /auth/verify-reset-otp` → xác minh OTP → nhận `reset_token`
    3. `POST /auth/reset-password` → đặt mật khẩu mới bằng `reset_token`

    **Bảo mật:** Luôn trả về cùng thông báo dù email có tồn tại hay không
    *(chống tấn công dò tìm email — email enumeration attack).*
    OTP hết hạn sau **15 phút**.
    """
    account = db.query(Account).filter(Account.email == payload.email).first()
    if account and settings.emails_enabled:
        otp = generate_otp()
        account.otp_code = otp
        account.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        account.otp_purpose = "RESET_PASSWORD"
        db.commit()
        email_data = generate_reset_otp_email(email_to=account.email, otp=otp, full_name=account.full_name)
        send_email(email_to=account.email, subject=email_data.subject, html_content=email_data.html_content)
    return Message(message="Nếu email này đã đăng ký, chúng tôi đã gửi mã OTP reset mật khẩu")


@router.post(
    "/resend-otp",
    response_model=Message,
    summary="Gửi lại mã OTP reset mật khẩu",
)
def resend_otp(payload: ResendOTPRequest, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.email == payload.email).first()
    if account and settings.emails_enabled:
        otp = generate_otp()
        account.otp_code = otp
        account.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        account.otp_purpose = "RESET_PASSWORD"
        db.commit()
        email_data = generate_reset_otp_email(email_to=account.email, otp=otp, full_name=account.full_name)
        send_email(email_to=account.email, subject=email_data.subject, html_content=email_data.html_content)
    return Message(message="Nếu email này đã đăng ký, chúng tôi đã gửi lại mã OTP reset mật khẩu")


@router.post(
    "/verify-reset-otp",
    response_model=VerifyResetOTPResponse,
    summary="Xác minh OTP để lấy token reset mật khẩu",
)
def verify_reset_otp(payload: VerifyResetOTPRequest, db: Session = Depends(get_db)):
    """
    **Bước 2 trong quy trình reset mật khẩu.**

    - **email**: email đã gửi OTP
    - **otp**: mã 6 chữ số nhận được qua email

    **Trả về:** `reset_token` — dùng ngay ở bước 3 (`POST /auth/reset-password`).
    Token này chỉ dùng một lần và hết hạn sau 1 giờ.
    """
    account = db.query(Account).filter(Account.email == payload.email).first()
    if not account:
        raise HTTPException(status_code=400, detail="Email hoặc OTP không hợp lệ")
    if account.otp_purpose != "RESET_PASSWORD" or account.otp_code != payload.otp:
        raise HTTPException(status_code=400, detail="OTP không hợp lệ")
    if account.otp_expires_at and account.otp_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP đã hết hạn — vui lòng yêu cầu OTP mới")
    account.otp_code = None
    account.otp_expires_at = None
    account.otp_purpose = None
    db.commit()
    token = generate_password_reset_token(email=account.email)
    return VerifyResetOTPResponse(reset_token=token, message="Xác minh OTP thành công")


@router.post(
    "/reset-password",
    response_model=Message,
    summary="Đặt mật khẩu mới bằng reset token",
)
def reset_password(body: NewPassword, db: Session = Depends(get_db)):
    """
    **Bước 3 — Đặt mật khẩu mới.**

    - **token**: `reset_token` nhận được từ bước 2
    - **new_password**: mật khẩu mới (tối thiểu 8 ký tự)

    Sau khi đặt mật khẩu thành công, đăng nhập lại bằng `POST /auth/login`.
    """
    email = verify_password_reset_token(token=body.token)
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token không hợp lệ hoặc đã hết hạn")
    account = db.query(Account).filter(Account.email == email).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token không hợp lệ")
    if not account.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đã bị vô hiệu hóa")
    account.password_hash = get_password_hash(body.new_password)
    db.commit()
    return Message(message="Đặt mật khẩu mới thành công")


# ─────────────────────────────────────────────────────────────
# ADMIN — QUẢN LÝ TÀI KHOẢN
# ─────────────────────────────────────────────────────────────

@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[ADMIN] Tạo tài khoản với role tùy chỉnh",
    dependencies=[Depends(get_current_active_superuser)],
)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    """
    **[Chỉ ADMIN]** Tạo tài khoản cho nhân viên nội bộ hoặc bệnh nhân.

    - **email**: email đăng nhập
    - **password**: mật khẩu ban đầu (hệ thống gửi email thông báo nếu SMTP được cấu hình)
    - **full_name**: họ tên đầy đủ
    - **role**: `ADMIN` hoặc `PATIENT`

    **Khi tạo tài khoản `PATIENT`:** Hồ sơ Patient cơ bản được tự động tạo kèm theo.
    Admin cần vào `PATCH /patients/{id}` để hoàn thiện thông tin (ngày sinh, SĐT, CCCD...).
    """
    existing = db.query(Account).filter(Account.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email này đã tồn tại trong hệ thống")
    account = Account(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
    )
    db.add(account)
    db.flush()
    if account.role == "PATIENT":
        from datetime import date as date_cls
        from app.models.patient import Patient
        name_parts = payload.full_name.split(" ", 1) if payload.full_name else ["Patient", ""]
        patient = Patient(
            patient_id=account.account_id,
            first_name=name_parts[1] if len(name_parts) > 1 else name_parts[0],
            last_name=name_parts[0] if len(name_parts) > 1 else "",
            dob=date_cls(2000, 1, 1),
        )
        db.add(patient)
    try:
        db.commit()
        db.refresh(account)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Email '{payload.email}' đã bị trùng")
    if settings.emails_enabled:
        email_data = generate_new_account_email(email_to=payload.email, full_name=payload.full_name, password=payload.password)
        send_email(email_to=payload.email, subject=email_data.subject, html_content=email_data.html_content)
    return account


@router.get(
    "/accounts",
    response_model=list[AccountResponse],
    summary="[ADMIN] Danh sách tất cả tài khoản",
    dependencies=[Depends(get_current_active_superuser)],
)
def list_accounts(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    """
    **[Chỉ ADMIN]** Liệt kê tất cả tài khoản trong hệ thống.

    - **skip**: bỏ qua N bản ghi đầu (phân trang)
    - **limit**: số lượng tối đa trả về (mặc định 100)
    """
    return db.query(Account).offset(skip).limit(limit).all()


@router.get(
    "/accounts/{account_id}",
    response_model=AccountResponse,
    summary="[ADMIN] Xem chi tiết một tài khoản",
)
def get_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_active_superuser),
):
    """
    **[Chỉ ADMIN]** Xem thông tin chi tiết tài khoản theo UUID.

    - **account_id**: UUID của tài khoản cần xem
    """
    account = db.query(Account).filter(Account.account_id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản")
    return account


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountResponse,
    summary="[ADMIN] Cập nhật thông tin tài khoản (role, email, trạng thái...)",
    dependencies=[Depends(get_current_active_superuser)],
)
def update_account(account_id: UUID, payload: AccountUpdate, db: Session = Depends(get_db)):
    """
    **[Chỉ ADMIN]** Sửa thông tin tài khoản — email, họ tên, role, trạng thái, mật khẩu.

    Tất cả các trường đều là tùy chọn (`exclude_unset`).
    Chỉ truyền những trường cần thay đổi.

    **Ví dụ đổi role sang ADMIN:**
    ```json
    { "role": "ADMIN" }
    ```
    """
    account = db.query(Account).filter(Account.account_id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản")
    if payload.email and payload.email != account.email:
        dup = db.query(Account).filter(Account.email == payload.email).first()
        if dup:
            raise HTTPException(status_code=409, detail="Email đã được dùng bởi tài khoản khác")
        account.email = payload.email
    if payload.full_name is not None:
        account.full_name = payload.full_name
    if payload.role is not None:
        account.role = payload.role
    if payload.is_active is not None:
        account.is_active = payload.is_active
    if payload.password:
        account.password_hash = get_password_hash(payload.password)
    db.commit()
    db.refresh(account)
    return account


@router.delete(
    "/accounts/{account_id}",
    response_model=Message,
    summary="[ADMIN] Vô hiệu hóa tài khoản (soft delete)",
)
def deactivate_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    admin: Account = Depends(get_current_active_superuser),
):
    """
    **[Chỉ ADMIN]** Vô hiệu hóa tài khoản — đặt `is_active=False`.

    Tài khoản bị vô hiệu hóa không thể đăng nhập nhưng dữ liệu lịch sử được giữ nguyên.
    Để khôi phục, dùng `PATCH /auth/accounts/{id}/reactivate`.

    **Lưu ý:** Admin không thể tự vô hiệu hóa tài khoản của chính mình.
    """
    if account_id == admin.account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không thể tự vô hiệu hóa tài khoản của mình")
    account = db.query(Account).filter(Account.account_id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản")
    if not account.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đã bị vô hiệu hóa trước đó")
    account.is_active = False
    db.commit()
    return Message(message="Tài khoản đã được vô hiệu hóa")


@router.patch(
    "/accounts/{account_id}/reactivate",
    response_model=Message,
    summary="[ADMIN] Kích hoạt lại tài khoản đã bị vô hiệu hóa",
    dependencies=[Depends(get_current_active_superuser)],
)
def reactivate_account(account_id: UUID, db: Session = Depends(get_db)):
    """
    **[Chỉ ADMIN]** Khôi phục tài khoản đã bị vô hiệu hóa.

    Sau khi kích hoạt lại, người dùng có thể đăng nhập bình thường.
    """
    account = db.query(Account).filter(Account.account_id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản")
    if account.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đang hoạt động bình thường")
    account.is_active = True
    db.commit()
    return Message(message="Tài khoản đã được kích hoạt lại")