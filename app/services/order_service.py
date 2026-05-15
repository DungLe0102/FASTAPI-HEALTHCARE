import re
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.patient import PatientBHYT, Patient
from app.models.inventory import Medication
from app.schemas.order import OrderCreate, OrderResponse
from app.services import notification_service

BASE_SALARY = Decimal("2340000")
BHYT_RATE = Decimal("0.045")
BHYT_MONTHLY_FEE = BASE_SALARY * BHYT_RATE # 105,300 VND

def _404(db: Session, model, col, val, label: str):
    obj = db.query(model).filter(col == val).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"{label} '{val}' not found"
        )
    return obj

def check_expired_orders(db: Session):
    """
    Background task or helper to cancel orders that pass their 10 minutes expiry.
    """
    expired_orders = db.query(Order).filter(
        Order.status == "PENDING",
        Order.expires_at < datetime.now()
    ).all()

    for order in expired_orders:
        order.status = "CANCELLED"
    
    if expired_orders:
        db.commit()

def create_order(db: Session, payload: OrderCreate) -> OrderResponse:
    # Trigger cancellation of expired orders before creating a new one
    check_expired_orders(db)

    _404(db, Patient, Patient.patient_id, payload.patient_id, "Patient")

    total_amount = Decimal("0")
    order_metadata = {}

    if payload.order_type == "BHYT_EXTENSION":
        if not payload.extension_months or not (6 <= payload.extension_months <= 12):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="BHYT extension must be between 6 and 12 months"
            )
        if not payload.bhyt_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="bhyt_id is required for BHYT_EXTENSION order"
            )
        
        bhyt = _404(db, PatientBHYT, PatientBHYT.bhyt_id, payload.bhyt_id, "Patient BHYT")
        
        total_amount = BHYT_MONTHLY_FEE * payload.extension_months
        order_metadata = {
            "bhyt_id": str(payload.bhyt_id),
            "bhyt_code": bhyt.bhyt_code,
            "extension_months": payload.extension_months
        }

    elif payload.order_type == "PHARMACY":
        if not payload.items or len(payload.items) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pharmacy order must contain items"
            )
        
        items_data = []
        for item in payload.items:
            medication = _404(db, Medication, Medication.medication_id, item.item_id, "Medication")
            if not medication.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Medication {medication.med_name} is no longer active"
                )
            from app.services.inventory_service import get_stock_total
            available_qty = get_stock_total(db, item.item_id)
            if available_qty < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Not enough stock for '{medication.med_name}'. Available: {available_qty}, requested: {item.quantity}"
                )
            
            line_total = medication.price * item.quantity
            total_amount += line_total
            
            items_data.append({
                "medication_id": str(medication.medication_id),
                "med_name": medication.med_name,
                "quantity": item.quantity,
                "price": float(medication.price),
                "line_total": float(line_total)
            })
            
        order_metadata = {"items": items_data}

    # 10 minutes expiry
    expires_at = datetime.now() + timedelta(minutes=10)

    order = Order(
        patient_id=payload.patient_id,
        order_type=payload.order_type,
        total_amount=total_amount,
        status="PENDING",
        expires_at=expires_at,
        order_metadata=order_metadata
    )
    
    db.add(order)
    db.commit()
    db.refresh(order)

    # Generate VietQR details
    transfer_content = f"PAYORD {order.order_id}"
    base_url = "https://img.vietqr.io/image/HDB-107704070005803-print.png"
    qr_url = f"{base_url}?amount={int(order.total_amount)}&addInfo={transfer_content}"

    response = OrderResponse.model_validate(order)
    response.qr_url = qr_url
    response.transfer_content = transfer_content

    return response

def process_order_payment_webhook(db: Session, item_description: str, item_amount: float, item_reference: str):
    """
    Thực hiện xử lý web hook thanh toán tương tự process_vietqr_webhook bên billing_service.
    Nội dung chuyển khoản chứa format "PAYORD <UUID>".
    """
    check_expired_orders(db)

    match = re.search(r"PAYORD\s+([a-fA-F0-9\-]{36})", item_description)
    if not match:
        return False
    
    try:
        order_id = UUID(match.group(1))
    except ValueError:
        return False
    
    order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()
    if not order or order.status != "PENDING":
        return False
        
    # Check expiry again inside transaction
    if order.expires_at < datetime.now():
        order.status = "CANCELLED"
        db.commit()
        return False

    if Decimal(str(item_amount)) < order.total_amount:
        # Paid amount is less than expected
        return False

    # Mark as PAID
    order.status = "PAID"
    
    # Trigger post-payment logic based on order_type
    if order.order_type == "BHYT_EXTENSION":
        meta = order.order_metadata
        bhyt_id = meta.get("bhyt_id")
        ext_months = meta.get("extension_months", 0)
        
        bhyt = db.query(PatientBHYT).filter(PatientBHYT.bhyt_id == bhyt_id).first()
        if bhyt:
            start_date = max(bhyt.valid_to, datetime.now().date())
            
            # Tính toán gia hạn thẻ
            new_month = start_date.month + ext_months
            new_year = start_date.year + (new_month - 1) // 12
            new_month = (new_month - 1) % 12 + 1
            
            # Handle edge case where the day might be out of range for the new month
            try:
                bhyt.valid_to = start_date.replace(year=new_year, month=new_month)
            except ValueError:
                # e.g. Feb 29 -> Feb 28 or 31st to 30th
                from calendar import monthrange
                last_day = monthrange(new_year, new_month)[1]
                bhyt.valid_to = start_date.replace(year=new_year, month=new_month, day=last_day)
                
            bhyt.last_extension_date = datetime.now().date()
            bhyt.check_status = "VERIFIED"
            
            notification_service.create_notification(db, {
                "recipient_id": order.patient_id,
                "recipient_type": "PATIENT",
                "title": "Gia hạn BHYT thành công",
                "content": f"BHYT {bhyt.bhyt_code} đã được gia hạn thêm {ext_months} tháng. Hạn mới: {bhyt.valid_to.strftime('%d/%m/%Y')}.",
                "notification_type": "PAYMENT"
            })
            
    elif order.order_type == "PHARMACY":
        # Trừ kho thuốc sau khi thanh toán thành công
        from app.services.inventory_service import _deduct_stock
        meta = order.order_metadata
        items = meta.get("items", [])
        for item in items:
            medication_id = UUID(item["medication_id"])
            qty = item["quantity"]
            # Lưu ý: _deduct_stock gọi HTTPException nếu thiếu hàng, 
            # tuy nhiên ở bước này khách đã trả tiền. Trong thực tế, nên check tồn kho 
            # kỹ lúc tạo đơn. Ở đây nếu thiếu hàng, nó sẽ rollback giao dịch và lỗi webhook.
            _deduct_stock(db, medication_id, qty)

        notification_service.create_notification(db, {
            "recipient_id": order.patient_id,
            "recipient_type": "PATIENT",
            "title": "Thanh toán đơn thuốc thành công",
            "content": f"Đơn thuốc của bạn (Mã: {order.order_id}) đã được thanh toán và đang được chuẩn bị.",
            "notification_type": "PAYMENT"
        })

    db.commit()
    return True
