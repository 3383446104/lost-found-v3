# app/dependencies/auth.py
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import uuid
from ..config import settings
from ..database import get_db_connection
from ..logger import logger

security = HTTPBearer(auto_error=False)

# 服务实例代际（boot id）：进程每次启动都会重新生成。
# 签发时写入 token 的 `boot` 声明，校验时与当前值比对 —— 一旦重启后端，
# 重启前签发的所有 token 立即失效，用户必须重新登录。
BOOT_ID = uuid.uuid4().hex


def create_access_token(data: Dict[str, Any]) -> str:
    """创建 JWT 访问令牌（短有效期 + 绑定当前服务实例）"""
    to_encode = data.copy()
    to_encode.pop("exp", None)
    to_encode.pop("boot", None)
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    to_encode.update({"exp": expire, "boot": BOOT_ID})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> Dict[str, Any] | None:
    """验证 JWT 令牌，返回 payload 或 None"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        logger.warning(f"Token 验证失败: {str(e)}")
        return None
    if payload.get("boot") != BOOT_ID:
        logger.warning("Token 属于上一次服务实例（后端已重启），视为失效")
        return None
    return payload


def renew_token_if_needed(response: Response, payload: Dict[str, Any]) -> None:
    """滑动续期：剩余有效期不足阈值时，在响应头下发新令牌。

    前端拦截器收到 ``X-Renewed-Token`` 后静默替换本地令牌。因此：
    - 只要在有效期内还有任意一次请求（页面开着时靠未读数轮询），会话就顺延；
    - 彻底离开页面超过 ACCESS_TOKEN_MINUTES 后不再有请求 → 令牌自然过期 → 必须重登。
    """
    exp = payload.get("exp")
    if not exp:
        return
    remaining = exp - datetime.now(timezone.utc).timestamp()
    # 默认「有效期 - 1 分钟」：每次鉴权请求都把令牌续到满期，
    # 这样最后一次请求之后再过一个完整有效期才失效，精确满足「离开满 N 分钟才重登」
    renew_minutes = settings.ACCESS_TOKEN_RENEW_MINUTES
    if renew_minutes is None:
        renew_minutes = max(settings.ACCESS_TOKEN_MINUTES - 1, 1)
    if remaining <= renew_minutes * 60:
        response.headers["X-Renewed-Token"] = create_access_token({
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
        })


async def get_current_user(
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> Dict[str, Any]:
    """获取当前登录用户（验证 token 并确保用户存在）"""
    # auto_error=False：未携带凭证时由我们自己返回 401，
    # 避免 HTTPBearer 默认的 403 与「账号被禁用」的 403 语义混淆
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证"
        )
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

    # 滑动续期：快到期时静默下发新令牌（前端拦截器负责替换）
    renew_token_if_needed(response, payload)

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