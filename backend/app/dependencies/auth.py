# app/dependencies/auth.py
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from ..config import settings
from ..database import get_db_connection
from ..logger import logger

security = HTTPBearer()


def create_access_token(data: Dict[str, Any]) -> str:
    """创建 JWT 访问令牌"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRATION)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> Dict[str, Any] | None:
    """验证 JWT 令牌，返回 payload 或 None"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        logger.warning(f"Token 验证失败: {str(e)}")
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """获取当前登录用户（验证 token 并确保用户存在）"""
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的 Token"
        )

    # 使用上下文管理器查询用户是否存在
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, role, status FROM users WHERE id = ?', (payload.get('user_id'),))
        user = cursor.fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )
    if user['status'] == 'deleted':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已注销"
        )
    if user['status'] == 'disabled':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员"
        )

    # 可选：记录成功访问日志（调试时用）
    # logger.debug(f"用户 {payload.get('user_id')} 认证成功")

    return payload


async def get_current_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """获取当前管理员用户（验证用户是否为管理员）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE id = ?', (current_user['user_id'],))
        user = cursor.fetchone()

    if not user or user['role'] != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )

    return current_user


def resolve_optional_viewer(request: Request) -> Dict[str, Any] | None:
    """公开接口的可选身份解析（C1）。

    用于 ``GET /items/`` 与 ``GET /items/{id}`` 这类**公开**端点：携带合法且
    账号状态为 ``active`` 的 token 时返回 ``{"user_id": int, "role": str}``，
    否则（无 token / token 非法 / 用户不存在 / status != 'active'）一律返回
    ``None``（降级为匿名），从而让 disabled / deleted 用户不再以「属主」身份
    看到未审核数据。

    与 ``get_current_user`` 的区别：本函数**不抛异常**——公开接口允许匿名访问，
    只是把禁用/注销身份降级掉。返回 ``role`` 以便 ``get_item`` 仍能识别管理员。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = verify_token(auth[7:])
    if not payload:
        return None
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, role, status FROM users WHERE id=?", (payload.get("user_id"),))
        row = cur.fetchone()
    if not row or row["status"] != "active":
        return None  # disabled / deleted / 不存在 → 降级为匿名
    return {"user_id": row["id"], "role": row["role"]}