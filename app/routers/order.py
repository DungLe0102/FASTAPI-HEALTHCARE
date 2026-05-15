"""
Router: Đơn hàng — Gia hạn BHYT & Mua thuốc trực tuyến
=========================================================
Prefix  : /api/v1
Tags    : Orders

Luồng đặt hàng:
  1. POST /orders/             — tạo đơn hàng → nhận mã QR thanh toán
  2. (Chờ bệnh nhân chuyển khoản theo nội dung PAYORD <order_id>)
  3. Ngân hàng gọi webhook → hệ thống xử lý tự động:
     - Gia hạn BHYT: cộng thêm tháng vào thẻ, đặt check_status = VERIFIED
     - Mua thuốc: trừ tồn kho, gửi thông báo chuẩn bị hàng
  4. POST /orders/check-expired — (Cron Job) hủy đơn quá 10 phút chưa thanh toán
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.schemas.order import OrderCreate, OrderResponse
from app.services import order_service
from app.security import get_current_account, require_roles
from app.models.account import Account

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo đơn hàng gia hạn BHYT hoặc mua thuốc trực tuyến",
)
def create_order(
    payload    : OrderCreate,
    db         : Session = Depends(get_db),
    current_acc: Account = Depends(get_current_account),
):
    """
    **Tạo đơn hàng trực tuyến — hỗ trợ 2 loại:**

    ---
    **Loại 1: Gia hạn thẻ BHYT** (`order_type = "BHYT_EXTENSION"`)

    ```json
    {
      "patient_id": "<uuid>",
      "order_type": "BHYT_EXTENSION",
      "bhyt_id": "<uuid>",
      "extension_months": 6
    }
    ```

    - **bhyt_id**: UUID thẻ BHYT cần gia hạn (lấy từ `GET /patients/{id}/bhyt`)
    - **extension_months**: số tháng gia hạn — chỉ chấp nhận **6 đến 12 tháng**
    - Tiền BHYT tính theo công thức: `4.5% × lương cơ sở (2.340.000đ) × số tháng`
      → VD: 6 tháng = `4.5% × 2.340.000 × 6 = 631.800đ`

    ---
    **Loại 2: Mua thuốc trực tuyến** (`order_type = "PHARMACY"`)

    ```json
    {
      "patient_id": "<uuid>",
      "order_type": "PHARMACY",
      "items": [
        { "item_id": "<medication_uuid>", "quantity": 2 }
      ]
    }
    ```

    - **items**: danh sách thuốc cần mua — ít nhất 1 loại
    - Hệ thống kiểm tra tồn kho trước khi tạo đơn

    ---
    **Response trả về:**
    - `order_id`: mã đơn hàng
    - `total_amount`: tổng tiền cần thanh toán
    - `qr_url`: URL mã QR VietQR (HDBank) — quét và chuyển khoản
    - `transfer_content`: nội dung chuyển khoản bắt buộc — dạng `PAYORD <order_id>`
    - `expires_at`: thời điểm đơn hàng bị hủy nếu chưa thanh toán (**sau 10 phút**)

    ⚠️ **Quan trọng:** Nội dung chuyển khoản phải khớp chính xác với `transfer_content`
    để webhook nhận biết và xử lý tự động.

    **Phân quyền:** Bệnh nhân chỉ được tạo đơn cho chính mình; ADMIN tạo được cho mọi bệnh nhân.
    """
    if current_acc.role == "PATIENT" and payload.patient_id != current_acc.account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Từ chối: Bệnh nhân chỉ được tạo đơn cho hồ sơ của chính mình",
        )
    return order_service.create_order(db, payload)


@router.post(
    "/check-expired",
    response_model=dict,
    summary="[CRON] Quét và hủy đơn hàng quá 10 phút chưa thanh toán",
)
def check_expired_orders(
    db: Session = Depends(get_db),
    _admin: Account = Depends(require_roles("ADMIN")),
):
    """
    **[Tác vụ hệ thống — gọi định kỳ bởi Cron Job]**

    Quét toàn bộ đơn hàng đang ở trạng thái `PENDING` và đã quá thời điểm `expires_at`,
    sau đó chuyển sang `CANCELLED` để giải phóng slot tồn kho.

    **Khuyến nghị:** Thiết lập Cron Job gọi mỗi 1 phút:
    ```
    * * * * * curl -X POST http://localhost:8000/api/v1/orders/check-expired
    ```

    Nếu không có Cron Job, hệ thống cũng tự kiểm tra mỗi khi có đơn hàng mới được tạo.
    Tuy nhiên, đơn hàng cũ quá hạn sẽ không được dọn sạch hoàn toàn.
    """
    order_service.check_expired_orders(db)
    return {"message": "Đã kiểm tra và hủy các đơn hàng quá hạn thanh toán"}
