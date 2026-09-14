# app/api/items.py
import os
import uuid
import asyncio
import functools
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request, BackgroundTasks
from fastapi.responses import FileResponse
from ..config import settings
from ..database import get_db_connection, vector_to_json, json_to_vector, CATEGORIES
from ..dependencies.auth import get_current_user, resolve_optional_viewer
from ..utils.file import allowed_file
from ..utils.time_utils import format_beijing_time
from ..clip_service import clip_service
from ..validators import validate_item_title, validate_contact
from ..logger import logger
from ..models.match import MatchRequest


router = APIRouter(prefix="/items", tags=["物品"])

# ---------- 配置默认值 ----------
MAX_UPLOAD_SIZE = getattr(settings, "MAX_UPLOAD_SIZE", 5 * 1024 * 1024)
ALLOWED_EXTENSIONS = getattr(settings, "ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "gif", "webp"})


def _match_threshold_default() -> float:
    """手动匹配默认下界（v3.5.0-R-T4）。

    **每次调用时**从 ``settings.MATCH_THRESHOLD_MANUAL`` 读取，与同模块的
    ``resolve_legend()`` 共享**同一数据源**。

    历史：旧实现 ``MATCH_THRESHOLD = getattr(settings, ...)`` 是**导入期快照**——
    与 ``resolve_legend()`` 的「每次访问 settings」语义不一致；线上通过环境变量
    调整 ``MATCH_THRESHOLD_MANUAL`` 后，旧快照仍读旧值，配置变更**只在图例**生效、
    实际过滤仍按旧值，行为割裂。
    """
    return float(settings.MATCH_THRESHOLD_MANUAL)


def resolve_legend() -> dict:
    """解析前端图例阈值（C5：图例派生，单一数据源）。

    ``legend.high`` = 能触发**自动推送**的区间下界（默认 = ``MATCH_THRESHOLD_AUTO``）；
    ``legend.mid``  = **手动匹配**的宽松下界（默认 = ``MATCH_THRESHOLD_MANUAL``）。
    ``MATCH_LEGEND_HIGH`` / ``MATCH_LEGEND_MID`` 为可选覆盖（None 即派生）。

    Returns:
        ``{"high": float, "mid": float}``，随 ``POST /match`` 响应的 ``legend`` 字段下发，
        彻底消除前端硬编码（v3.4.1：前端 0.75/0.5 vs 后端 0.20）割裂。
    """
    high = settings.MATCH_LEGEND_HIGH
    mid = settings.MATCH_LEGEND_MID
    if high is None:
        high = settings.MATCH_THRESHOLD_AUTO
    if mid is None:
        mid = settings.MATCH_THRESHOLD_MANUAL
    return {"high": float(high), "mid": float(mid)}


# ---------- 辅助函数 ----------
def _query_dim(query_img_vec, query_text_vec) -> Optional[int]:
    """当前模型输出的向量维度（= 查询向量长度；无图无文 → ``None``）。

    以**实际查询向量长度**为准（而非 config 声明值）：它才真正反映
    「当前运行模型」的输出维度，可同时覆盖「切了模型但库未重嵌入」的场景。
    """
    if query_img_vec is not None:
        return len(query_img_vec)
    if query_text_vec is not None:
        return len(query_text_vec)
    return None


def _assert_vector_dims_match(query_dim: Optional[int], target_items) -> None:
    """R2 维度预检：库中目标向量维度 ≠ 当前模型维度 → 抛 ``HTTPException(500)``。

    动机：打分循环的 ``except → continue`` 会把「未重嵌入导致的 ``np.dot`` 维度不符」
    **静默**吞成「匹配为空」（HTTP 200 + ``matches: []``），与「真的没找到」外观一致
    → 全站匹配静默失效。此预检在**逐条打分前**把该情形变成**明确错误**，
    提示先运行重嵌入脚本。
    """
    if query_dim is None:
        return
    for item in target_items:
        for col in ("image_vector", "text_vector"):
            vec = json_to_vector(item[col]) if item[col] else None
            if vec is not None and len(vec) != query_dim:
                raise HTTPException(
                    500,
                    f"向量维度不匹配（库中 {len(vec)} 维 / 当前模型 {query_dim} 维），"
                    "请先运行 scripts/reembed_all_vectors.py 重嵌入",
                )


def is_safe_path(base_dir: str, target_path: str) -> bool:
    base = os.path.abspath(base_dir)
    target = os.path.abspath(os.path.join(base, os.path.basename(target_path)))
    return os.path.commonpath([base, target]) == base

async def run_in_threadpool(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    if kwargs:
        func = functools.partial(func, **kwargs)
    return await loop.run_in_executor(None, func, *args)

def delete_file_if_exists(file_path: str):
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning(f"删除文件失败: {file_path}, 错误: {e}")

def is_temp_file(file_path: str) -> bool:
    return file_path and os.path.basename(file_path).startswith("temp_")

# ---------- 接口 ----------
@router.post("/", status_code=201)
async def create_item(
        type: str = Form(...),
        title: str = Form(...),
        description: str = Form(""),
        category: str = Form("其他"),
        contact: str = Form(""),
        location: str = Form(""),
        image: Optional[UploadFile] = File(None),
        current_user: dict = Depends(get_current_user)
):
    """发布物品（失物/招领）"""
    if type not in ['lost', 'found']:
        raise HTTPException(400, "物品类型无效")

    valid, msg = validate_item_title(title)
    if not valid:
        raise HTTPException(400, msg)
    valid, msg = validate_contact(contact)
    if not valid:
        raise HTTPException(400, msg)

    if image == "":
        image = None

    image_path = None
    image_vector = None
    color_vector = None
    if image is not None and image.filename:
        content = await image.read()
        if not allowed_file(image.filename, content):
            raise HTTPException(400, "文件类型不支持")
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(400, f"图片大小不能超过 {MAX_UPLOAD_SIZE//1024//1024}MB")
        ext = os.path.splitext(image.filename)[1][1:].lower()
        filename = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
        image_path = os.path.join(settings.UPLOAD_FOLDER, filename)
        try:
            with open(image_path, "wb") as f:
                f.write(content)
        except Exception as e:
            logger.error(f"保存图片失败: {e}")
            raise HTTPException(500, "图片上传失败，请稍后重试")

        try:
            image_vector = await run_in_threadpool(clip_service.get_image_feature, image_path)
            # R4：同步计算 27 维颜色直方图并随物品持久化，匹配时免重复磁盘 IO
            color_vector = await run_in_threadpool(clip_service.get_color_histogram, image_path)
        except Exception as e:
            delete_file_if_exists(image_path)
            logger.error(f"图片特征提取失败: {e}")
            raise HTTPException(500, "图片特征提取失败")

    text_vector = None
    full_text = f"{title} {description}".strip()
    if full_text:
        try:
            text_vector = await run_in_threadpool(clip_service.get_text_feature, full_text)
        except Exception as e:
            delete_file_if_exists(image_path)
            logger.error(f"文本特征提取失败: {e}")
            raise HTTPException(500, "文本特征提取失败")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO items (type, title, description, category, image_path,
                                   image_vector, text_vector, color_vector, contact, location, status, user_id, review_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (type, title, description, category, image_path,
                  vector_to_json(image_vector), vector_to_json(text_vector), vector_to_json(color_vector),
                  contact, location, 'pending', current_user['user_id'], 'pending'))
            item_id = cursor.lastrowid
    except Exception as e:
        delete_file_if_exists(image_path)
        logger.error(f"数据库插入失败: {e}")
        raise HTTPException(500, "发布失败，请检查内容后重试")

    logger.info(f"用户 {current_user['user_id']} 发布了物品 {item_id}")
    return {"success": True, "id": item_id}


@router.get("/")
async def get_items(
    request: Request,
    type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    keyword: Optional[str] = Query(""),
    user_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """获取物品列表（首页统一规则：已审核+活跃 OR 自己的物品，管理员也不例外）"""
    # C1：公开接口身份统一经 resolve_optional_viewer 解析；
    # 无/非法 token 或 status!='active'（disabled/deleted）一律降级为匿名。
    viewer = resolve_optional_viewer(request)
    viewer_id = viewer["user_id"] if viewer else None

    with get_db_connection() as conn:
        cursor = conn.cursor()
        base_query = """SELECT id, type, title, description, category, image_path, contact,
                          location, status, review_status, user_id, created_at, review_time
                   FROM items WHERE 1=1"""
        count_query = "SELECT COUNT(*) AS total FROM items WHERE 1=1"
        params = []
        count_params = []

        # 统一规则：已审核+活跃的物品 OR 自己的物品(排除已找回/已关闭)
        viewer_param = viewer_id if viewer_id else -1
        base_query += " AND ( (review_status = 'approved' AND status = 'active') OR (user_id = ? AND status NOT IN ('claimed', 'closed')) )"
        count_query += " AND ( (review_status = 'approved' AND status = 'active') OR (user_id = ? AND status NOT IN ('claimed', 'closed')) )"
        params.append(viewer_param)
        count_params.append(viewer_param)

        if user_id:
            base_query += " AND user_id = ?"
            count_query += " AND user_id = ?"
            params.append(user_id)
            count_params.append(user_id)
        if type:
            base_query += " AND type = ?"
            count_query += " AND type = ?"
            params.append(type)
            count_params.append(type)

        if category:
            base_query += " AND category = ?"
            count_query += " AND category = ?"
            params.append(category)
            count_params.append(category)
        if keyword:
            base_query += " AND (title LIKE ? OR description LIKE ?)"
            count_query += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f'%{keyword}%', f'%{keyword}%'])
            count_params.extend([f'%{keyword}%', f'%{keyword}%'])

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']

        base_query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(base_query, params)
        items = [dict(row) for row in cursor.fetchall()]

    for item in items:
        item['created_at'] = format_beijing_time(item.get('created_at'))
        item['review_time'] = format_beijing_time(item.get('review_time'))

    return {"items": items, "total": total}


@router.get("/categories")
async def get_categories():
    """获取类别列表"""
    return {"categories": CATEGORIES}


@router.get("/uploads/{filename:path}")
async def uploaded_file(filename: str):
    """访问图片（公开）"""
    base_name = os.path.basename(filename)
    if '..' in base_name or '/' in base_name or '\\' in base_name:
        raise HTTPException(400, "非法文件名")
    file_path = os.path.join(settings.UPLOAD_FOLDER, base_name)
    if not os.path.exists(file_path):
        raise HTTPException(404, "图片不存在")
    return FileResponse(file_path)


@router.get("/{item_id:int}")
async def get_item(item_id: int, request: Request):
    """获取物品详情（公开，未审核物品仅限发布者/管理员查看）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")

    # C1：公开接口身份统一经 resolve_optional_viewer 解析；
    # 无/非法 token 或 status!='active'（disabled/deleted）降级为匿名，
    # 从而不再以「属主」身份放行自己的未审核物品。
    viewer = resolve_optional_viewer(request)
    viewer_id = viewer["user_id"] if viewer else None
    is_admin = bool(viewer and viewer["role"] == "admin")

    if not (is_admin or item['user_id'] == viewer_id):
        if item['review_status'] != 'approved' or item['status'] != 'active':
            raise HTTPException(404, "物品不存在")

    result = dict(item)
    result.pop('image_vector', None)
    result.pop('text_vector', None)
    if not (is_admin or result['user_id'] == viewer_id):
        result.pop('user_id', None)
    result['created_at'] = format_beijing_time(result.get('created_at'))
    result['review_time'] = format_beijing_time(result.get('review_time'))
    return {"item": result}


@router.put("/{item_id:int}/mark-claimed")
async def mark_item_claimed(
    item_id: int,
    current_user: dict = Depends(get_current_user)
):
    """发布者标记物品已找回/已认领（自标记，替代原确认/拒绝流程）"""
    user_id = current_user['user_id']

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, user_id, title, type, status FROM items WHERE id = ?',
            (item_id,)
        )
        item = cursor.fetchone()

        if not item:
            raise HTTPException(404, "物品不存在")
        if item['user_id'] != user_id:
            cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
            u = cursor.fetchone()
            if not u or u['role'] != 'admin':
                raise HTTPException(403, "仅物品发布者可标记")
        if item['status'] != 'active':
            raise HTTPException(400, "该物品已处理或不可操作")

        cursor.execute(
            "UPDATE items SET status = 'claimed' WHERE id = ?",
            (item_id,)
        )
        cursor.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND link = ? AND (title LIKE '%认领%' OR title LIKE '%归还%')",
            (user_id, f"/items/{item_id}")
        )

        action_label = '已找回' if item['type'] == 'lost' else '已归还'

    # 事务已提交，计数器 +1
    from ..database import increment_counter
    increment_counter('total_claimed', 1)

    logger.info(f"用户 {user_id} 将物品 {item_id} 标记为 {action_label}")
    return {"success": True, "message": f"物品已标记为{action_label}", "new_status": "claimed"}


@router.put("/{item_id:int}")
async def update_item(
    item_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """编辑物品（本人或管理员）"""
    user_id = current_user['user_id']

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, image_path, image_vector, color_vector, type, review_status, status FROM items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")

        cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if item['user_id'] != user_id and user['role'] != 'admin':
            raise HTTPException(403, "无权修改此物品")

    form = await request.form()
    title = form.get('title')
    description = form.get('description', '')
    category = form.get('category', '其他')
    contact = form.get('contact', '')
    location = form.get('location', '')
    if not title:
        raise HTTPException(400, "标题不能为空")

    # 添加输入验证
    valid, msg = validate_item_title(title)
    if not valid:
        raise HTTPException(400, msg)
    valid, msg = validate_contact(contact)
    if not valid:
        raise HTTPException(400, msg)

    new_image_path = item['image_path']
    image_vector = None
    color_vector = None
    if 'image' in form:
        file = form['image']
        if file and file.filename:
            content = await file.read()
            if not allowed_file(file.filename, content):
                raise HTTPException(400, "文件类型不支持")
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(400, f"图片大小不能超过 {MAX_UPLOAD_SIZE//1024//1024}MB")
            ext = os.path.splitext(file.filename)[1][1:].lower()
            filename = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
            temp_path = os.path.join(settings.UPLOAD_FOLDER, filename)
            try:
                with open(temp_path, "wb") as f:
                    f.write(content)
            except Exception as e:
                logger.error(f"保存新图片失败: {e}")
                raise HTTPException(500, "图片上传失败，请稍后重试")

            try:
                image_vector = await run_in_threadpool(clip_service.get_image_feature, temp_path)
                # R4：换图时必须同步更新颜色直方图，否则留下脏数据
                color_vector = await run_in_threadpool(clip_service.get_color_histogram, temp_path)
            except Exception as e:
                delete_file_if_exists(temp_path)
                logger.error(f"新图片特征提取失败: {e}")
                raise HTTPException(500, "图片特征提取失败")

            old_path = new_image_path
            new_image_path = temp_path
            delete_file_if_exists(old_path)

    text_vector = None
    full_text = f"{title} {description}".strip()
    if full_text:
        try:
            text_vector = await run_in_threadpool(clip_service.get_text_feature, full_text)
        except Exception as e:
            if new_image_path != item['image_path']:
                delete_file_if_exists(new_image_path)
            logger.error(f"文本特征提取失败: {e}")
            raise HTTPException(500, "文本特征提取失败")

    image_vector_json = vector_to_json(image_vector) if image_vector is not None else item['image_vector']
    # R4：换图时 color_vector 已重算；未换图时保留库中原值（避免脏数据 / 丢特征）
    color_vector_json = vector_to_json(color_vector) if color_vector is not None else item['color_vector']
    review_status = item['review_status']
    status = item['status']
    reviewer_id = None
    review_time = None
    reject_reason = None
    if user['role'] != 'admin' and review_status != 'pending':
        review_status = 'pending'
        status = 'pending'

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE items SET
                title = ?, description = ?, category = ?,
                contact = ?, location = ?, image_path = ?,
                image_vector = ?, text_vector = ?, color_vector = ?,
                review_status = ?, status = ?,
                reviewer_id = ?, review_time = ?, reject_reason = ?
            WHERE id = ?
        ''', (title, description, category, contact, location,
              new_image_path, image_vector_json,
              vector_to_json(text_vector), color_vector_json, review_status, status,
              reviewer_id, review_time, reject_reason, item_id))

    # 如果是从驳回状态重新提交，标记旧驳回通知为已读
    if item['review_status'] == 'rejected':
        from ..database import add_notification
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE notifications SET is_read=1 WHERE user_id=? AND link=? AND title LIKE '%驳回%'",
                (user_id, f"/items/{item_id}")
            )

    logger.info(f"用户 {user_id} 更新了物品 {item_id}")
    return {"success": True, "id": item_id}


@router.delete("/{item_id:int}")
async def delete_item(
    item_id: int,
    current_user: dict = Depends(get_current_user)
):
    """删除物品（本人或管理员），使用 rowcount 检查防止并发"""
    user_id = current_user['user_id']

    # 先获取图片路径用于删除文件
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, image_path FROM items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")

        # 检查权限
        cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if item['user_id'] != user_id and user['role'] != 'admin':
            raise HTTPException(403, "无权删除此物品")

        # 执行删除，检查影响行数
        cursor.execute('DELETE FROM items WHERE id = ?', (item_id,))
        if cursor.rowcount == 0:
            raise HTTPException(404, "物品已不存在")
        # 保存图片路径以备删除
        image_path = item['image_path']

    # 事务已提交，删除图片文件
    delete_file_if_exists(image_path)
    logger.info(f"用户 {user_id} 删除了物品 {item_id}")
    return {"success": True}


@router.post("/match")
async def match_items(req: MatchRequest, current_user: dict = Depends(get_current_user)):
    """智能匹配（基于图片或文本描述，需登录）"""
    if not req.image_path and not req.text:
        raise HTTPException(400, "需要提供图片路径或文本描述")

    if req.target_type not in ('lost', 'found'):
        raise HTTPException(400, "target_type 必须为 'lost' 或 'found'")

    image_path = None
    if req.image_path:
        filename = os.path.basename(req.image_path)
        image_path = os.path.join(settings.UPLOAD_FOLDER, filename)
        if not is_safe_path(settings.UPLOAD_FOLDER, image_path):
            raise HTTPException(400, "图片路径不合法")
        if not os.path.exists(image_path):
            if req.text:
                logger.warning(f"临时图片不存在，转为文本匹配: {req.image_path}")
                image_path = None
            else:
                raise HTTPException(404, "图片文件不存在")

    query_img_vec = None
    query_text_vec = None
    query_color_vec = None
    try:
        if image_path:
            query_img_vec = await run_in_threadpool(clip_service.get_image_feature, image_path)
            query_color_vec = await run_in_threadpool(clip_service.get_color_histogram, image_path)
        if req.text:
            query_text_vec = await run_in_threadpool(clip_service.get_text_feature, req.text)
    except Exception as e:
        logger.error(f"特征提取失败: {e}")
        raise HTTPException(500, "特征提取失败")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, title, description, image_vector, text_vector, color_vector, image_path, category, location, created_at
            FROM items
            WHERE type = ? AND status = 'active' AND review_status = 'approved'
        ''', (req.target_type,))
        target_items = cursor.fetchall()

    threshold = req.threshold if req.threshold is not None else _match_threshold_default()

    # 匹配来源（按查询实际可用输入判定）：仅文 → text；仅图 → image；图文 → mixed。
    if query_img_vec is not None and query_text_vec is not None:
        match_source = "mixed"
    elif query_img_vec is not None:
        match_source = "image"
    else:
        match_source = "text"

    # R2 维度预检：在逐条打分前拦截「模型维度 ≠ 库中向量维度」，避免静默返回空集
    _assert_vector_dims_match(_query_dim(query_img_vec, query_text_vec), target_items)

    results = []
    skipped = 0
    for item in target_items:
        target_img_vec = json_to_vector(item['image_vector'])
        target_text_vec = json_to_vector(item['text_vector'])
        # 颜色特征：优先取库中已持久化的 color_vector（R4，免重复磁盘 IO）；
        # 缺失（NULL，老数据尚未回填）时才回退实时计算，保证老数据不炸。
        target_color_vec = json_to_vector(item['color_vector']) if item['color_vector'] else None
        if target_color_vec is None and item['image_path']:
            try:
                target_color_vec = await run_in_threadpool(clip_service.get_color_histogram, item['image_path'])
            except Exception as e:
                logger.warning(f"物品 {item['id']} 颜色直方图回退计算失败: {e}")
                target_color_vec = None
        # 时间衰减（兼容 SQLite "YYYY-MM-DD HH:MM:SS" 和 ISO 格式）
        try:
            ts = str(item['created_at'])
            target_date = None
            for fmt in (None, '%Y-%m-%d %H:%M:%S'):
                try:
                    target_date = datetime.fromisoformat(ts.replace('Z', '+00:00')) if fmt is None else datetime.strptime(ts[:19], fmt).replace(tzinfo=timezone.utc)
                    break
                except Exception:
                    continue
            if target_date is None:
                days_old = 0
            else:
                days_old = max(0, (datetime.now(timezone.utc) - target_date).days)
        except Exception:
            days_old = 0
        try:
            similarity = await run_in_threadpool(
                clip_service.compute_weighted_similarity,
                query_img_vec, query_text_vec, target_img_vec, target_text_vec,
                cat1=req.category or '', cat2=item['category'] or '',
                loc1=req.location or '', loc2=item['location'] or '',
                days_old=days_old,
                color1=query_color_vec, color2=target_color_vec,
            )
        except Exception as e:
            skipped += 1
            logger.error(f"匹配物品 {item['id']} 时打分出错（已跳过）: {e}")
            continue
        logger.info(f"  匹配计算: 物品{item['id']} 相似度={similarity:.4f}")
        if similarity >= threshold:
            results.append({
                'id': item['id'],
                'title': item['title'],
                'description': item['description'],
                'category': item['category'],
                'location': item['location'],
                'image_path': item['image_path'],
                'similarity': round(similarity, 4),
                'match_source': match_source,
                'created_at': item['created_at'],
            })

    results.sort(key=lambda x: x['similarity'], reverse=True)

    if not results:
        # 区分「真的没找到」与「全挂了」：若所有目标都因异常被跳过，属系统性错误
        # （如维度不符/特征损坏），必须记 ERROR，避免运维把「模型不兼容」误当「无命中」。
        if target_items and skipped == len(target_items):
            logger.error(
                f"手动匹配全部失败：{skipped}/{len(target_items)} 条目标打分均抛异常，"
                "**并非「未找到」**！疑似模型维度不匹配（未重嵌入）或特征损坏，"
                "请检查并运行 scripts/reembed_all_vectors.py"
            )
        logger.info(
            f"手动匹配无结果: target_type={req.target_type} target_items_count={len(target_items)} "
            f"threshold={threshold} has_image={query_img_vec is not None} has_text={query_text_vec is not None} "
            f"skipped={skipped}"
        )

    if image_path and is_temp_file(image_path):
        delete_file_if_exists(image_path)

    return {"matches": results[:20], "legend": resolve_legend()}


@router.post("/{item_id:int}/claim")
async def claim_item(
    item_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """申请认领/归还物品（发送站内通知 + 邮件给物品发布者）"""
    user_id = current_user['user_id']

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, user_id, title, status, review_status, type FROM items WHERE id = ?',
            (item_id,)
        )
        item = cursor.fetchone()

        if not item:
            raise HTTPException(404, "物品不存在")
        if item['user_id'] == user_id:
            raise HTTPException(400, "不能操作自己的物品")
        if item['status'] != 'active' or item['review_status'] != 'approved':
            raise HTTPException(400, "该物品当前不可操作")

        # 检查是否已有待处理的申请
        cursor.execute(
            "SELECT id FROM notifications WHERE user_id = ? AND link = ? AND is_read = 0 AND (title LIKE '%认领%' OR title LIKE '%归还%')",
            (item['user_id'], f"/items/{item_id}")
        )
        if cursor.fetchone():
            raise HTTPException(400, "已发送申请，请等待回复")

        # 获取申请人信息（含手机号）
        cursor.execute(
            'SELECT username, phone FROM users WHERE id = ?', (user_id,)
        )
        claimer = cursor.fetchone()
        claimer_phone = claimer['phone'] or '未填写'

        # 获取物品发布者信息（用于邮件通知）
        cursor.execute(
            'SELECT username, email FROM users WHERE id = ?', (item['user_id'],)
        )
        owner = cursor.fetchone()

        # 根据物品类型生成不同的通知文案
        # lost=失物(发布者丢了东西) → 别人捡到要"归还"给发布者
        # found=拾物(发布者捡了东西) → 别人来"认领"自己丢的东西
        if item['type'] == 'lost':
            action_word = '归还'
        else:
            action_word = '认领'

        title = f"[{action_word}申请] 用户 '{claimer['username']}' 想要{action_word}您的物品"
        content = f"物品 '{item['title']}' 收到{action_word}申请。申请人联系方式：{claimer_phone}。请及时联系确认。"
        link = f"/items/{item_id}"

        cursor.execute(
            'INSERT INTO notifications (user_id, title, content, link) VALUES (?, ?, ?, ?)',
            (item['user_id'], title, content, link)
        )

    # 发送邮件通知（后台任务，不阻塞事件循环；同步 send_email 会自动进线程池）
    if owner and owner['email']:
        try:
            from ..utils.email_utils import send_email
            subject = f"【校园失物检索】您的物品 '{item['title']}' 有新的{action_word}申请"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f7fc;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
                    <h2 style="color: #2c3e50;">校园失物检索平台</h2>
                    <p style="font-size: 16px; color: #333;">亲爱的 <strong>{owner['username']}</strong>：</p>
                    <p style="font-size: 15px; color: #444;">用户 <strong>{claimer['username']}</strong> 想要{action_word}您发布的物品 <strong>"{item['title']}"</strong>。</p>
                    <p style="font-size: 14px; color: #666;">📞 申请人联系方式：<strong>{claimer_phone}</strong></p>
                    <p style="margin: 24px 0;">
                        <a href="{settings.BASE_URL}/items/{item_id}" style="display: inline-block; padding: 10px 24px; background: #1B4D3E; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 500;">查看详情</a>
                    </p>
                    <hr style="border: none; border-top: 1px solid #eaeef2; margin: 24px 0;">
                    <p style="font-size: 12px; color: #999;">—— 校园失物检索平台 · 自动通知 ——</p>
                </div>
            </body>
            </html>
            """
            background_tasks.add_task(send_email, owner['email'], subject, body, True)
        except Exception as e:
            logger.warning(f"发送认领邮件失败: {e}")

    return {"success": True, "message": f"{action_word}申请已发送，请等待物品发布者确认"}


@router.post("/temp-upload")
async def temp_upload(
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """临时上传图片（供匹配使用），文件将在匹配后自动删除"""
    if not image or not image.filename:
        raise HTTPException(400, "请选择图片")
    content = await image.read()
    if not allowed_file(image.filename, content):
        raise HTTPException(400, "文件类型不支持")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"图片大小不能超过 {MAX_UPLOAD_SIZE//1024//1024}MB")

    ext = os.path.splitext(image.filename)[1][1:].lower()
    temp_filename = f"temp_{uuid.uuid4().hex}.{ext}" if ext else f"temp_{uuid.uuid4().hex}"
    temp_path = os.path.join(settings.UPLOAD_FOLDER, temp_filename)
    try:
        with open(temp_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"临时文件保存失败: {e}")
        raise HTTPException(500, "文件保存失败")

    return {"path": temp_filename, "success": True}
