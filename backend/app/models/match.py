# app/models/match.py
from pydantic import BaseModel
from typing import Optional

class MatchRequest(BaseModel):
    """智能匹配请求参数"""
    image_path: Optional[str] = None
    text: Optional[str] = None
    target_type: str = "found"          # 匹配目标类型：lost 或 found
    threshold: Optional[float] = None   # 相似度阈值

class MatchResult(BaseModel):
    item_id: int
    title: str
    description: Optional[str]
    category: Optional[str]
    image_path: Optional[str]
    similarity: float

class MatchResponse(BaseModel):
    matches: list[MatchResult]

class MatchConfirm(BaseModel):
    is_confirmed: bool = True