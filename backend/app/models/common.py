# app/models/common.py
from pydantic import BaseModel
from typing import TypeVar, Generic, List

T = TypeVar('T')

class PagedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    size: int
    items: List[T]