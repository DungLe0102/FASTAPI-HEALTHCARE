from uuid import UUID
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel


class AuditLogCreate(BaseModel):
    actor_id         : UUID
    actor_role       : str
    action_type      : Literal["CREATE", "UPDATE", "DELETE", "READ"]
    target_table     : str
    target_record_id : UUID
    ip_address       : Optional[str] = None

class AuditLogResponse(AuditLogCreate):
    log_id    : UUID
    timestamp : datetime
    model_config = {"from_attributes": True}