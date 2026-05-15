from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal

class OrderItemSchema(BaseModel):
    item_id: UUID
    quantity: int

class OrderCreate(BaseModel):
    patient_id: UUID
    order_type: str = Field(..., pattern="^(BHYT_EXTENSION|PHARMACY)$")
    
    # Dùng cho BHYT_EXTENSION
    bhyt_id: Optional[UUID] = None
    extension_months: Optional[int] = Field(None, ge=6, le=12)
    
    # Dùng cho PHARMACY
    items: Optional[List[OrderItemSchema]] = None

class OrderResponse(BaseModel):
    order_id: UUID
    patient_id: UUID
    order_type: str
    total_amount: Decimal
    status: str
    created_at: datetime
    expires_at: datetime
    order_metadata: Optional[Dict[str, Any]] = None
    qr_url: Optional[str] = None
    transfer_content: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
