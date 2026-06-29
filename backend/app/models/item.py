# app/models/item.py
from typing import Optional, Literal
from pydantic import BaseModel, Field

ItemStatus = Literal['pending', 'active', 'claimed', 'done', 'rejected', 'closed']
ItemType = Literal['lost', 'found']
ReviewStatus = Literal['pending', 'approved', 'rejected']


class ItemCreate(BaseModel):
    type: ItemType
    title: str = Field(..., min_length=2, max_length=50)
    description: str = ""
    category: str = "其他"
    contact: str = ""
    location: str = ""


class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = None
    category: Optional[str] = None
    contact: Optional[str] = None
    location: Optional[str] = None
    status: Optional[ItemStatus] = None


class ItemResponse(BaseModel):
    id: int
    type: ItemType
    title: str
    description: Optional[str]
    category: Optional[str]
    image_path: Optional[str]
    contact: Optional[str]
    location: Optional[str]
    status: ItemStatus
    user_id: int
    review_status: ReviewStatus
    created_at: str
    updated_at: Optional[str]
    review_time: Optional[str]