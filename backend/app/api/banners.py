# app/api/banners.py
# 轮播图（v3.6.0 融合：首页轮播内容运营模块）
#
# 设计要点（移植自参考项目 campus-lost-and-found-ai）：
# - 标题/图/描述/可选跳转 + sort_no 升序展示 + 启停
# - 图片存 UPLOAD_FOLDER（banner_ 前缀持久文件），复用 /items/uploads/ 静态路由
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from ..config import settings
from ..database import get_db_connection
from ..dependencies.auth import get_current_admin
from ..utils.file import allowed_file
from ..utils.time_utils import format_beijing_time
from ..logger import logger


router = APIRouter(prefix="/banners", tags=["轮播图"])

MAX_UPLOAD_SIZE = getattr(settings, "MAX_UPLOAD_SIZE", 5 * 1024 * 1024)


# ---------- 请求模型 ----------
class BannerCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    image_path: str = Field(..., min_length=1, max_length=255, description="图片文件名（先经 /banners/upload 上传）")
    description: Optional[str] = Field(None, max_length=500)
    link_url: Optional[str] = Field(None, max_length=255)
    sort_no: int = Field(0, ge=0, description="升序展示")
    status: int = Field(1, ge=0, le=1, description="1启用 / 0停用")


class BannerUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    image_path: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    link_url: Optional[str] = Field(None, max_length=255)
    sort_no: Optional[int] = Field(None, ge=0)
    status: Optional[int] = Field(None, ge=0, le=1)


# ---------- 接口 ----------
@router.get("")
async def list_banners():
    """公开轮播列表（仅启用，按 sort_no 升序）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, title, image_path, description, link_url, sort_no
               FROM banners WHERE status = 1 ORDER BY sort_no ASC, id ASC"""
        )
        banners = [dict(r) for r in cur.fetchall()]
    return {"banners": banners}


@router.post("/upload")
async def upload_banner(
    image: UploadFile = File(...),
    current_admin: dict = Depends(get_current_admin)
):
    """上传轮播图片（banner_ 前缀持久文件）"""
    if not image or not image.filename:
        raise HTTPException(400, "请选择图片")
    content = await image.read()
    if not allowed_file(image.filename, content):
        raise HTTPException(400, "文件类型不支持")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"图片大小不能超过 {MAX_UPLOAD_SIZE//1024//1024}MB")

    ext = os.path.splitext(image.filename)[1][1:].lower()
    filename = f"banner_{uuid.uuid4().hex}.{ext}" if ext else f"banner_{uuid.uuid4().hex}"
    file_path = os.path.join(settings.UPLOAD_FOLDER, filename)
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"轮播图保存失败: {e}")
        raise HTTPException(500, "文件保存失败")

    return {"path": filename, "success": True}


@router.get("/admin")
async def admin_banners(current_admin: dict = Depends(get_current_admin)):
    """管理端轮播列表（全量）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, title, image_path, description, link_url, sort_no, status, created_at
               FROM banners ORDER BY sort_no ASC, id DESC"""
        )
        banners = []
        for r in cur.fetchall():
            d = dict(r)
            d["created_at"] = format_beijing_time(d.get("created_at"))
            banners.append(d)
    return {"banners": banners}


@router.post("/admin", status_code=201)
async def create_banner(
    payload: BannerCreate,
    current_admin: dict = Depends(get_current_admin)
):
    """新增轮播图"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO banners (title, image_path, description, link_url, sort_no, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payload.title, payload.image_path, payload.description,
             payload.link_url, payload.sort_no, payload.status),
        )
        banner_id = cur.lastrowid
    logger.info(f"管理员 {current_admin['user_id']} 新增轮播图 {banner_id}")
    return {"success": True, "id": banner_id}


@router.put("/admin/{banner_id:int}")
async def update_banner(
    banner_id: int,
    payload: BannerUpdate,
    current_admin: dict = Depends(get_current_admin)
):
    """修改轮播图（仅更新提供的字段）"""
    sets, params = [], []
    for field in ("title", "image_path", "description", "link_url", "sort_no", "status"):
        value = getattr(payload, field)
        if value is not None:
            sets.append(f"{field}=?")
            params.append(value)

    if not sets:
        raise HTTPException(400, "没有需要更新的字段")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM banners WHERE id=?", (banner_id,))
        if not cur.fetchone():
            raise HTTPException(404, "轮播图不存在")

        cur.execute(
            f"UPDATE banners SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            params + [banner_id],
        )

    logger.info(f"管理员 {current_admin['user_id']} 修改轮播图 {banner_id}")
    return {"success": True}


@router.delete("/admin/{banner_id:int}")
async def delete_banner(
    banner_id: int,
    current_admin: dict = Depends(get_current_admin)
):
    """删除轮播图（同时清理磁盘图片）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM banners WHERE id=?", (banner_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "轮播图不存在")
        image_path = row["image_path"]
        cur.execute("DELETE FROM banners WHERE id=?", (banner_id,))

    if image_path:
        file_path = os.path.join(settings.UPLOAD_FOLDER, os.path.basename(image_path))
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                logger.warning(f"删除轮播图片失败: {file_path}, 错误: {e}")

    logger.info(f"管理员 {current_admin['user_id']} 删除轮播图 {banner_id}")
    return {"success": True}
