# app/api/auth.py
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from ..models.user import UserRegister, UserLogin, ProfileUpdate
from ..database import get_db_connection
from ..dependencies.auth import create_access_token, get_current_user
from ..config import settings
from ..utils.file import allowed_file
from ..logger import logger
import bcrypt
import sqlite3

router = APIRouter(tags=["认证"])

MAX_UPLOAD_SIZE = getattr(settings, "MAX_UPLOAD_SIZE", 5 * 1024 * 1024)


def check_unique_contact(conn, phone: str, email: str, exclude_user_id: int = None):
    """校验手机号和邮箱唯一性（空值跳过；注销账号不占号）。

    exclude_user_id 用于更新时排除自身。**注销（status='deleted'）的账号释放联系方式**：
    历史软删除测试账号不再挡住新注册与「改回原联系方式」。
    """
    if phone:
        cur = conn.cursor()
        if exclude_user_id:
            cur.execute(
                "SELECT id FROM users WHERE phone=? AND id!=? AND status != 'deleted'",
                (phone, exclude_user_id),
            )
        else:
            cur.execute("SELECT id FROM users WHERE phone=? AND status != 'deleted'", (phone,))
        if cur.fetchone():
            raise HTTPException(400, "该手机号已被其他账户使用")
    if email:
        cur = conn.cursor()
        if exclude_user_id:
            cur.execute(
                "SELECT id FROM users WHERE email=? AND id!=? AND status != 'deleted'",
                (email, exclude_user_id),
            )
        else:
            cur.execute("SELECT id FROM users WHERE email=? AND status != 'deleted'", (email,))
        if cur.fetchone():
            raise HTTPException(400, "该邮箱已被其他账户使用")


@router.post("/register", status_code=201)
async def register(user: UserRegister):
    """用户注册"""
    password_hash = bcrypt.hashpw(
        user.password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    with get_db_connection() as conn:
        cursor = conn.cursor()
        check_unique_contact(conn, user.phone, user.email or "")
        try:
            cursor.execute('''
                INSERT INTO users (username, password_hash, phone, email)
                VALUES (?, ?, ?, ?)
            ''', (user.username, password_hash, user.phone, user.email))
            user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="用户名已存在")

    token = create_access_token({"user_id": user_id, "username": user.username})
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "username": user.username,
            "role": "user",
            "status": "active"
        }
    }


@router.post("/login")
async def login(user: UserLogin):
    """用户登录"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, role, status, password_hash FROM users WHERE username = ?', (user.username,))
        db_user = cursor.fetchone()

    if not db_user:
        raise HTTPException(status_code=401, detail="用户不存在")

    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user['password_hash'].encode('utf-8')):
        raise HTTPException(status_code=401, detail="密码错误")

    if db_user['status'] == 'disabled':
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
    if db_user['status'] == 'deleted':
        raise HTTPException(status_code=403, detail="账号已注销")

    token = create_access_token({"user_id": db_user['id'], "username": db_user['username']})
    return {
        "success": True,
        "token": token,
        "user": {
            "id": db_user['id'],
            "username": db_user['username'],
            "role": db_user['role'],
            "status": db_user['status']
        }
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, nickname, student_no, avatar_path, role, status, phone, email, created_at FROM users WHERE id = ?', (current_user['user_id'],))
        user = cursor.fetchone()

    return {
        "user": {
            "id": user['id'],
            "username": user['username'],
            "nickname": user['nickname'],
            "student_no": user['student_no'],
            "avatar_path": user['avatar_path'],
            "role": user['role'],
            "status": user['status'],
            "phone": user['phone'],
            "email": user['email'],
            "created_at": user['created_at']
        }
    }


@router.put("/me")
async def update_profile(
    payload: ProfileUpdate,
    current_user: dict = Depends(get_current_user)
):
    """更新个人资料（密码/邮箱/手机号）"""
    # 转为「仅含请求显式提供字段」的 dict，使下方分支逻辑与旧 dict 版本完全等价
    payload = payload.model_dump(exclude_unset=True)
    user_id = current_user['user_id']
    updates = []
    params = []

    # 更新昵称
    if 'nickname' in payload:
        nickname = payload['nickname'].strip()
        if len(nickname) < 1 or len(nickname) > 30:
            raise HTTPException(400, "昵称长度 1-30 位")
        updates.append("nickname = ?")
        params.append(nickname)

    # 更新用户名
    if 'username' in payload and payload['username']:
        new_uname = payload['username'].strip()
        if len(new_uname) < 2 or len(new_uname) > 20:
            raise HTTPException(400, "用户名长度 2-20 位")
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT id FROM users WHERE username = ? AND id != ?', (new_uname, user_id))
            if cur.fetchone():
                raise HTTPException(400, "用户名已被占用")
        updates.append("username = ?")
        params.append(new_uname)

    # 更新密码
    if 'password' in payload and payload['password']:
        new_pw = payload['password'].strip()
        if len(new_pw) < 6 or len(new_pw) > 30:
            raise HTTPException(400, "密码长度 6-30 位")
        password_hash = bcrypt.hashpw(
            new_pw.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        updates.append("password_hash = ?")
        params.append(password_hash)

    # 更新邮箱
    if 'email' in payload:
        email = payload['email'].strip()
        if email and not ('@' in email and '.' in email):
            raise HTTPException(400, "邮箱格式不正确")
        updates.append("email = ?")
        params.append(email if email else None)

    # 更新手机号
    if 'phone' in payload:
        phone = payload['phone'].strip()
        if phone and not (len(phone) == 11 and phone.startswith('1')):
            raise HTTPException(400, "手机号格式不正确")
        updates.append("phone = ?")
        params.append(phone if phone else None)

    if not updates:
        raise HTTPException(400, "没有需要更新的字段")

    # 手机/邮箱唯一性校验（排除自身）
    new_phone = next((p for p, k in zip(params, updates) if 'phone' in k), None)
    new_email = next((p for p, k in zip(params, updates) if 'email' in k), None)
    with get_db_connection() as conn:
        check_unique_contact(conn, new_phone or "", new_email or "", user_id)

    params.append(user_id)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params
        )

    return {"success": True, "message": "资料更新成功"}


@router.post("/me/avatar")
async def upload_avatar(
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """上传头像（avatar_ 前缀持久文件，存 uploads 根目录，复用 /items/uploads/ 静态路由）"""
    if not image or not image.filename:
        raise HTTPException(400, "请选择图片")
    content = await image.read()
    if not allowed_file(image.filename, content):
        raise HTTPException(400, "仅支持 JPG/PNG 图片")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"图片大小不能超过 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")

    ext = os.path.splitext(image.filename)[1][1:].lower()
    filename = f"avatar_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(settings.UPLOAD_FOLDER, filename)
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"头像保存失败: {e}")
        raise HTTPException(500, "文件保存失败")

    # 更新头像路径并清理旧头像文件
    with get_db_connection() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT avatar_path FROM users WHERE id = ?", (current_user['user_id'],)).fetchone()
        old_avatar = row["avatar_path"] if row else None
        cur.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (filename, current_user['user_id']))

    if old_avatar and old_avatar != filename:
        old_path = os.path.join(settings.UPLOAD_FOLDER, os.path.basename(old_avatar))
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                logger.warning(f"旧头像清理失败: {old_path}")

    return {"success": True, "path": filename}


@router.delete("/me")
async def delete_account(current_user: dict = Depends(get_current_user)):
    """注销账号（软删除：标记为 deleted，关闭所有物品）"""
    user_id = current_user['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 关闭所有活跃物品
        cursor.execute(
            "UPDATE items SET status='closed' WHERE user_id=? AND status IN ('active','pending')",
            (user_id,)
        )
        # 软删除用户（用户名加后缀，状态置 deleted）
        cursor.execute(
            "UPDATE users SET username=username || '_deleted_' || id, status='deleted' WHERE id=?",
            (user_id,)
        )
    return {"success": True, "message": "账号已注销"}


@router.get("/me/history")
async def get_my_history(current_user: dict = Depends(get_current_user)):
    """获取当前用户的历史记录（所有物品 + 认领记录）"""
    user_id = current_user['user_id']

    with get_db_connection() as conn:
        cur = conn.cursor()

        # 我发布的所有物品
        cur.execute(
            "SELECT id, type, title, category, status, image_path, created_at "
            "FROM items WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        my_items = [dict(r) for r in cur.fetchall()]

        # 我发起的认领记录（通过通知表反查）
        cur.execute(
            "SELECT id, title, content, link, created_at "
            "FROM notifications WHERE user_id = ? AND (title LIKE '%申请%' OR content LIKE '%申请%') "
            "ORDER BY created_at DESC",
            (user_id,)
        )
        my_claims_raw = [dict(r) for r in cur.fetchall()]

        # 我收到的通知（别人认领我的物品）
        cur.execute(
            "SELECT id, title, content, link, created_at "
            "FROM notifications WHERE user_id = ? AND (title LIKE '%申请%' OR title LIKE '%认领%' OR title LIKE '%归还%') "
            "ORDER BY created_at DESC",
            (user_id,)
        )
        received_claims = [dict(r) for r in cur.fetchall()]

    return {
        "success": True,
        "data": {
            "my_items": my_items,
            "my_claims": my_claims_raw,
            "received_claims": received_claims
        }
    }