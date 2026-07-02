# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from .config import settings
from .logger import logger
from .database import init_db

# ---- 生命周期管理 ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    logger.info("正在启动应用...")
    init_db()
    logger.info("数据库初始化完成")
    yield
    logger.info("正在关闭应用...")

# ---- 创建应用 ----
app = FastAPI(
    title="校园失物检索平台 API",
    description="基于 CLIP 多模态匹配的校园失物检索平台",
    version="2.0.0",
    lifespan=lifespan
)

# ---- CORS 配置 ----
import re

class LocalhostRegexOrigin:
    """允许所有 localhost 端口的开发环境 CORS 策略"""
    _pattern = re.compile(r"^http://localhost:\d+$")

    @classmethod
    def match(cls, origin: str) -> bool:
        if not origin:
            return False
        return bool(cls._pattern.match(origin))

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://localhost:\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 注册路由 ----
from .api.auth import router as auth_router
from .api.items import router as items_router
from .api.admin import router as admin_router
from .api.notifications import router as notifications_router
from .api.stats import router as stats_router
from .api.announcements import router as announcements_router

app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(items_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(notifications_router, prefix=settings.API_V1_STR)
app.include_router(stats_router, prefix=settings.API_V1_STR)
app.include_router(announcements_router, prefix=settings.API_V1_STR)

# ---- 全局异常处理 ----
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "服务器内部错误，请稍后重试"}
    )

# ---- 根路径 ----
@app.get("/")
async def root():
    return {
        "message": "校园失物检索平台 API v2.0",
        "docs": "/docs",
        "status": "running"
    }

# ---- 健康检查 ----
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ---- 启动入口 ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )