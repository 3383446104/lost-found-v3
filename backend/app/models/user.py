# app/models/user.py
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=20)
    password: str = Field(..., min_length=6, max_length=30)
    phone: str = Field(..., min_length=11, max_length=11)
    email: Optional[EmailStr] = None

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', v):
            raise ValueError('用户名只能包含字母、数字、下划线或中文')
        return v

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r'^1[3-9]\d{9}$', v):
            raise ValueError('手机号格式不正确，请输入11位有效手机号')
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class ProfileUpdate(BaseModel):
    """个人资料更新请求（宽松模型：字段全可选，校验逻辑保留在 handler 内）。

    仅做结构声明，不加约束，确保与改动前的手写 ``payload`` 分支行为等价
    （空字典 → 400「没有需要更新的字段」；长度/格式校验仍由 handler 抛出 400）。
    """
    username: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None