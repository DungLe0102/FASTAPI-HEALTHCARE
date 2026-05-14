from uuid import UUID
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.notification import Notification, SupportRequest
from app.models.patient      import PatientBHYT
from app.models.account      import Account
from app.schemas.notification import NotificationCreate, SupportRequestCreate, SupportRequestUpdate
from app.config import settings
from app.utils import send_email, generate_notification_email


def _404(db: Session, model, col, val, label: str):
    obj = db.query(model).filter(col == val).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"{label} '{val}' not found"
        )
    return obj


# ── Notifications ─────────────────────────────────

def create_notification(db: Session, payload: NotificationCreate) -> Notification:
    # Accept both Pydantic payloads and plain dicts (some services call this internally).
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    notif = Notification(**data)
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # 🚀 Gửi Email ngay lập tức (Sync for simplicity as requested)
    if settings.emails_enabled:
        acc = db.query(Account).filter(Account.account_id == notif.recipient_id).first()
        if acc and acc.email:
            try:
                email_data = generate_notification_email(
                    email_to=acc.email,
                    title=notif.title,
                    content=notif.content,
                    full_name=acc.full_name
                )
                send_email(
                    email_to=acc.email,
                    subject=email_data.subject,
                    html_content=email_data.html_content
                )
                notif.status = "SENT"
                notif.sent_at = datetime.now()
                db.commit()
            except Exception as e:
                notif.status = "FAILED"
                db.commit()
    
    return notif

def list_notifications(
    db            : Session,
    recipient_id  : Optional[UUID] = None,
    status_filter : Optional[str]  = None,
    skip: int = 0, limit: int = 50,
) -> List[Notification]:
    q = db.query(Notification)
    if recipient_id:
        q = q.filter(Notification.recipient_id == recipient_id)
    if status_filter:
        q = q.filter(Notification.status == status_filter)
    return q.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()

def mark_sent(db: Session, notification_id: UUID) -> Notification:
    notif = _404(db, Notification, Notification.notification_id, notification_id, "Notification")
    
    # 🛑 Tránh update lại sent_at nếu đã gửi thành công trước đó
    if notif.status == "SENT":
        return notif
        
    notif.status  = "SENT"
    notif.sent_at = datetime.now()
    db.commit()
    db.refresh(notif)
    return notif

def mark_failed(db: Session, notification_id: UUID) -> Notification:
    notif = _404(db, Notification, Notification.notification_id, notification_id, "Notification")
    
    # 🛑 Nếu retry quá 5 lần thì chuyển thành DEAD/CANCELED để worker ngừng gửi
    notif.retry_count += 1
    if notif.retry_count >= 5:
        notif.status = "CANCELED"
    else:
        notif.status = "FAILED"
        
    db.commit()
    db.refresh(notif)
    return notif

def get_pending_notifications(db: Session, limit: int = 100) -> List[Notification]:
    """
    Sử dụng skip_locked=True để hỗ trợ Multi-worker. 
    Worker nào query trúng dòng nào sẽ khóa dòng đó lại, tránh gửi trùng lặp.
    """
    return (
        db.query(Notification)
        .filter(Notification.status.in_(["PENDING", "FAILED"]))
        .order_by(Notification.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )

def create_bhyt_expiry_alerts(db: Session, days_before: int = 30) -> int:
    """Cron job tạo thông báo BHYT sắp hết hạn."""
    cutoff = date.today() + timedelta(days=days_before)
    expiring = db.query(PatientBHYT).filter(
        PatientBHYT.valid_to     <= cutoff,
        PatientBHYT.valid_to     >= date.today(),
        PatientBHYT.is_active    == True,
        PatientBHYT.check_status == "VERIFIED",
    ).all()

    count = 0
    # 🛑 Chỉ quét trùng lặp trong vòng 60 ngày gần nhất để năm sau hàm này vẫn hoạt động
    sixty_days_ago = datetime.now() - timedelta(days=60)
    
    # Lấy danh sách patient_id
    patient_ids = [bhyt.patient_id for bhyt in expiring]
    
    # Query tất cả notification đã gửi cho những bệnh nhân này trong 60 ngày qua
    existing_notifications = db.query(Notification.recipient_id).filter(
        Notification.recipient_id.in_(patient_ids),
        Notification.notification_type == "BHYT_EXPIRATION",
        Notification.status.in_(["PENDING", "SENT"]),
        Notification.created_at >= sixty_days_ago
    ).all()
    
    # Tạo set các recipient_id đã nhận thông báo
    notified_patient_ids = {n[0] for n in existing_notifications}
    
    for bhyt in expiring:
        if bhyt.patient_id not in notified_patient_ids:
            db.add(Notification(
                recipient_id      = bhyt.patient_id,
                recipient_type    = "PATIENT",
                notification_type = "BHYT_EXPIRATION",
                channel           = "EMAIL", # Có thể map với push notification trên App
                title             = "Thẻ BHYT sắp hết hạn",
                content           = f"Thẻ BHYT {bhyt.bhyt_code} sẽ hết hạn vào {bhyt.valid_to.strftime('%d/%m/%Y')}. Vui lòng gia hạn để không ảnh hưởng đến quyền lợi khám chữa bệnh.",
            ))
            count += 1
            
    if count:
        db.commit()
    return count


# ── Support Requests ──────────────────────────────

def create_support_request(db: Session, payload: SupportRequestCreate) -> SupportRequest:
    req = SupportRequest(**payload.model_dump())
    db.add(req)
    db.commit()
    db.refresh(req)

    # 🚀 Thông báo cho Bệnh nhân đã nhận được yêu cầu
    create_notification(db, {
        "recipient_id": req.patient_id,
        "title": "Yêu cầu hỗ trợ đã được tiếp nhận",
        "content": f"Yêu cầu hỗ trợ về '{req.request_type}' của bạn đã được gửi thành công. Chúng tôi sẽ xử lý trong thời gian sớm nhất.",
        "type": "HR_SUPPORT"
    })
    return req

def list_support_requests(
    db            : Session,
    status_filter : Optional[str] = None,
    priority      : Optional[str] = None,
    skip: int = 0, limit: int = 50,
) -> List[SupportRequest]:
    q = db.query(SupportRequest)
    if status_filter:
        q = q.filter(SupportRequest.status == status_filter)
    if priority:
        q = q.filter(SupportRequest.priority == priority)
    return q.order_by(SupportRequest.created_at.desc()).offset(skip).limit(limit).all()

def update_support_request(
    db        : Session,
    request_id: UUID,
    payload   : SupportRequestUpdate,
) -> SupportRequest:
    req = _404(db, SupportRequest, SupportRequest.request_id, request_id, "SupportRequest")
    
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(req, k, v)
        
    # 🛑 Ghi nhận thời gian đóng ticket HOẶC clear thời gian nếu mở lại ticket
    if payload.status in ("RESOLVED", "CLOSED"):
        if not req.resolved_at:
            req.resolved_at = datetime.now()
    elif payload.status in ("OPEN", "IN_PROGRESS"):
        req.resolved_at = None
        
    db.commit()
    db.refresh(req)

    # 🚀 Thông báo cho Bệnh nhân khi trạng thái thay đổi (RESOLVED/CLOSED)
    if payload.status in ("RESOLVED", "CLOSED"):
        create_notification(db, {
            "recipient_id": req.patient_id,
            "title": f"Yêu cầu hỗ trợ {payload.status}",
            "content": f"Yêu cầu hỗ trợ của bạn đã được chuyển sang trạng thái {payload.status}. Cảm ơn bạn đã phản hồi.",
            "notification_type": "HR_SUPPORT"
        })

    return req