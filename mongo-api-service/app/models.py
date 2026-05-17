from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    value: float = 0.0


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    value: Optional[float] = None


class ItemResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    value: float
    created_at: datetime
    updated_at: datetime
