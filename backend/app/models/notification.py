# app/models/notification.py
from pydantic import BaseModel
from typing import Optional


class NotificationResponse(BaseModel):
    id: int
    title: str
    content: str
    link: Optional[str]
    is_read: bool
    created_at: str