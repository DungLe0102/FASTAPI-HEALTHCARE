from uuid import UUID
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query, status
from app.db import get_db
from app.models.audit  import AuditLog
from app.schemas.audit import AuditLogCreate, AuditLogResponse

# 👉 IMPORT BẢO MẬT
from app.security import require_roles
from app.models.account import Account


# ── Service ───────────────────────────────────────

def write_log(db: Session, payload: AuditLogCreate) -> AuditLog:
    log = AuditLog(**payload.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log) # Thêm refresh để trả về ID và Timestamp chuẩn từ DB
    return log

def query_logs(
    db              : Session,
    actor_id        : Optional[UUID] = None,
    target_table    : Optional[str]  = None,
    target_record_id: Optional[UUID] = None,
    action_type     : Optional[str]  = None,
    from_dt         : Optional[datetime] = None,
    to_dt           : Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[AuditLog]:
    q = db.query(AuditLog)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if target_table:
        q = q.filter(AuditLog.target_table == target_table)
    if target_record_id:
        q = q.filter(AuditLog.target_record_id == target_record_id)
    if action_type:
        q = q.filter(AuditLog.action_type == action_type)
    if from_dt:
        q = q.filter(AuditLog.timestamp >= from_dt)
    if to_dt:
        q = q.filter(AuditLog.timestamp <= to_dt)
    return q.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()


# ── Router ────────────────────────────────────────

router = APIRouter(prefix="", tags=["7. System - Inventory & Audit"])

@router.get(
    "/audit-logs", 
    response_model=List[AuditLogResponse],
    summary="Query audit trail (ADMIN only)"
)
def get_audit_logs(
    actor_id        : Optional[UUID]     = Query(None),
    target_table    : Optional[str]      = Query(None),
    target_record_id: Optional[UUID]     = Query(None),
    action_type     : Optional[str]      = Query(None),
    from_dt         : Optional[datetime] = Query(None),
    to_dt           : Optional[datetime] = Query(None),
    skip            : int                = Query(0,   ge=0),
    limit           : int                = Query(100, ge=1, le=500),
    db              : Session            = Depends(get_db),
    # 🔒 Chỉ ADMIN mới được xem log hệ thống
    current_acc     : Account            = Depends(require_roles("ADMIN")),
):
    return query_logs(db, actor_id, target_table, target_record_id, action_type, from_dt, to_dt, skip, limit)

@router.post(
    "/audit-logs", 
    response_model=AuditLogResponse, 
    status_code=status.HTTP_201_CREATED,
    summary="Write an audit log entry (internal / middleware use)"
)
def create_log(
    payload: AuditLogCreate, 
    db: Session = Depends(get_db),
    # 🔒 BỊT LỖ HỔNG: Yêu cầu quyền SYSTEM hoặc ADMIN để ghi log qua API
    current_acc: Account = Depends(require_roles("ADMIN")) 
):
    return write_log(db, payload)
