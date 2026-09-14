# app/models/admin.py
"""管理员端点请求模型（R9）。

统一原则：**模型只做结构声明，不给约束**——避免把现有手写校验的 400
变成 Pydantic 的 422，也避免改变字段可选性。原有校验与错误码全部保留在
handler 内，确保行为与改动前完全等价。
"""
from typing import List, Optional

from pydantic import BaseModel


class BatchApproveRequest(BaseModel):
    """批量审核通过请求（``POST /admin/reviews/batch-approve``）。"""
    item_ids: List[int] = []


class UserUpdateRequest(BaseModel):
    """用户状态/角色更新请求（``PUT /admin/users/{user_id}``）。

    注意：``role`` 保持 ``None`` 默认值，handler 用
    ``role if role is not None else "user"`` 还原原有语义
    （不可写成 ``role or "user"``，否则空字符串会被当成缺省）。
    """
    action: str = ""
    role: Optional[str] = None


class AdminCreateUserRequest(BaseModel):
    """管理员新增用户请求（``POST /admin/users``）。"""
    username: str = ""
    password: str = ""
    phone: str = ""
    email: str = ""
    role: str = "user"


class BatchItemsRequest(BaseModel):
    """批量操作物品请求（``POST /admin/items/batch``）。"""
    ids: List[int] = []
    action: str = ""


class ItemStatusUpdate(BaseModel):
    """管理员修改物品状态请求（``PUT /admin/items/{item_id}/status``）。"""
    status: str = ""
