# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from ..models.user import UserRegister, UserLogin
from ..database import get_db_connection
from ..dependencies.auth import create_access_token, get_current_user
import bcrypt
import sqlite3

router = APIRouter(tags=["认证"])


@router.post("/register", status_code=201)
async def register(user: UserRegister):
    """用户注册"""
    password_hash = bcrypt.hashpw(
        user.password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    with get_db_connection() as conn:
        cursor = conn.cursor()
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
        "user": {"id": user_id, "username": user.username}
    }


@router.post("/login")
async def login(user: UserLogin):
    """用户登录"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, role, password_hash FROM users WHERE username = ?', (user.username,))
        db_user = cursor.fetchone()

    if not db_user:
        raise HTTPException(status_code=401, detail="用户不存在")

    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user['password_hash'].encode('utf-8')):
        raise HTTPException(status_code=401, detail="密码错误")

    token = create_access_token({"user_id": db_user['id'], "username": db_user['username']})
    return {
        "success": True,
        "token": token,
        "user": {
            "id": db_user['id'],
            "username": db_user['username'],
            "role": db_user['role']
        }
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, role, phone, email, created_at FROM users WHERE id = ?', (current_user['user_id'],))
        user = cursor.fetchone()

    return {
        "user": {
            "id": user['id'],
            "username": user['username'],
            "role": user['role'],
            "phone": user['phone'],
            "email": user['email'],
            "created_at": user['created_at']
        }
    }


@router.put("/me")
async def update_profile(
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """更新个人资料（密码/邮箱/手机号）"""
    user_id = current_user['user_id']
    updates = []
    params = []

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

    params.append(user_id)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params
        )

    return {"success": True, "message": "资料更新成功"}