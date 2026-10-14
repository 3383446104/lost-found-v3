# app/api/categories.py
# 物品分类管理（v3.6.0 融合：分类表化 + 排序 + 使用中保护）
#
# 设计要点（移植自参考项目 campus-lost-and-found-ai）：
# - 分类由数据库 categories 表驱动（init_db 已种子 7 类），items.category 仍存 TEXT
# - 管理员可增/改名/删（被物品使用中的分类拒绝删除）；改名不追溯历史物品
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..database import get_db_connection
from ..dependencies.auth import get_current_admin
from ..logger import logger


router = APIRouter(prefix="/categories", tags=["分类"])


# ---------- 请求模型 ----------
class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=20)
    sort_no: int = Field(0, ge=0)


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=20)
    sort_no: Optional[int] = Field(None, ge=0)


# ---------- 接口 ----------
@router.get("/admin")
async def admin_categories(current_admin: dict = Depends(get_current_admin)):
    """管理端分类列表（含物品使用计数）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT c.id, c.name, c.sort_no,
                      (SELECT COUNT(*) FROM items i WHERE i.category = c.name) AS item_count
               FROM categories c
               ORDER BY c.sort_no ASC, c.id ASC"""
        )
        categories = [dict(r) for r in cur.fetchall()]
    return {"categories": categories}


@router.post("/admin", status_code=201)
async def create_category(
    payload: CategoryCreate,
    current_admin: dict = Depends(get_current_admin)
):
    """新增分类"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "分类名不能为空")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM categories WHERE name=?", (name,))
        if cur.fetchone():
            raise HTTPException(400, "分类已存在")
        try:
            cur.execute(
                "INSERT INTO categories (name, sort_no) VALUES (?, ?)",
                (name, payload.sort_no),
            )
        except Exception:
            raise HTTPException(400, "分类已存在")
        cat_id = cur.lastrowid

    logger.info(f"管理员 {current_admin['user_id']} 新增分类 '{name}'")
    return {"success": True, "id": cat_id}


@router.put("/admin/{cat_id:int}")
async def update_category(
    cat_id: int,
    payload: CategoryUpdate,
    current_admin: dict = Depends(get_current_admin)
):
    """改名/调整排序（改名不追溯历史物品的 category 字段）"""
    sets, params = [], []
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, "分类名不能为空")
        sets.append("name=?")
        params.append(name)
    if payload.sort_no is not None:
        sets.append("sort_no=?")
        params.append(payload.sort_no)
    if not sets:
        raise HTTPException(400, "没有需要更新的字段")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM categories WHERE id=?", (cat_id,))
        if not cur.fetchone():
            raise HTTPException(404, "分类不存在")
        try:
            cur.execute(
                f"UPDATE categories SET {', '.join(sets)} WHERE id=?",
                params + [cat_id],
            )
        except Exception:
            raise HTTPException(400, "分类名已存在")

    logger.info(f"管理员 {current_admin['user_id']} 修改分类 {cat_id}")
    return {"success": True}


@router.delete("/admin/{cat_id:int}")
async def delete_category(
    cat_id: int,
    current_admin: dict = Depends(get_current_admin)
):
    """删除分类（已被物品使用的分类拒绝删除）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM categories WHERE id=?", (cat_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "分类不存在")

        cur.execute("SELECT COUNT(*) AS c FROM items WHERE category=?", (row["name"],))
        if cur.fetchone()["c"] > 0:
            raise HTTPException(400, "该分类已被物品使用，无法删除")

        cur.execute("DELETE FROM categories WHERE id=?", (cat_id,))

    logger.info(f"管理员 {current_admin['user_id']} 删除分类 '{row['name']}'")
    return {"success": True}
