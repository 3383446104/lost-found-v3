# app/main.py
import threading
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from .config import settings
from .logger import logger
from .database import init_db
from .clip_service import clip_service

# 预热用的固定文本：只走文本塔，不依赖任何用户数据/图片文件
_CLIP_WARMUP_TEXT = "校园失物招领平台模型预热"


def _warmup_clip_model() -> None:
    """后台预热 CLIP 模型（v3.6.3）。

    背景：``Chinese-CLIP ViT-H/14`` 首次加载需 **8~18 秒**（3.6GB 权重、957.6M 参数，
    且 ``cn_clip`` 在 CPU 上会把权重 fp32→fp16→fp32 来回转换），而前端 axios 全局超时
    只有 10 秒。原先这段耗时落在「启动后第一个发布/匹配请求」上，导致用户看到
    ``timeout of 10000ms exceeded``，但后端其实已经成功入库。

    为什么用后台线程而不是在 lifespan 里同步加载：
    - 同步 await 会让端口在这 8~18 秒内**不监听**，前端先启动时会直接连接失败；
    - 后台线程则「端口先可用、模型随后就绪」，预热期间进来的业务请求会在
      ``_ensure_loaded`` 的加载锁上排队，加载完成后立即返回（不会再重复加载）。

    失败只记警告、不阻断启动：缺依赖/缺权重时其余接口仍可用，
    真正需要编码时由 ``_ensure_loaded`` 再抛一次明确错误。
    """
    started = time.time()
    logger.info("开始预热 CLIP 模型（后台线程，预计 8~18s，期间勿重复重启后端）...")
    try:
        clip_service.get_text_feature(_CLIP_WARMUP_TEXT)
    except Exception as exc:  # 预热是优化项，失败不应影响服务可用性
        logger.warning(
            "CLIP 预热失败（%.1fs）：%s；首个业务请求时将重新尝试加载",
            time.time() - started, exc,
        )
        return
    logger.info(
        "CLIP 预热完成，耗时 %.1fs；此后发布/匹配请求不再承担模型加载开销",
        time.time() - started,
    )


# ---- 生命周期管理 ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    logger.info("正在启动应用...")
    init_db()
    logger.info("数据库初始化完成")

    # ---- 启动横幅：把「跑的是哪套打分口径」写进日志（v3.7.0）----
    # WHY：uvicorn 不带 --reload 时，改完代码不重启就仍执行旧模块。
    # 没有这行日志，只能靠「阈值是多少」反推口径，排查成本极高
    # （2026-11-10 真实踩坑：进程仍是 legacy，日志打印 threshold=0.624956，
    #   而仓库里早已是 v2/0.6763，被误判为算法没生效）。
    from .config import match_threshold  # 局部导入，避免与 settings 初始化顺序耦合
    logger.info(
        "打分口径 MATCH_SCORING_MODE=%s ｜ 阈值 manual=%.4f auto=%.4f email=%.4f"
        " ｜ V2_TITLE_GATE=%s V2_SYNONYM_ENABLED=%s",
        settings.MATCH_SCORING_MODE,
        match_threshold("manual"), match_threshold("auto"), match_threshold("email"),
        getattr(settings, "V2_TITLE_GATE", "-"),
        getattr(settings, "V2_SYNONYM_ENABLED", "-"),
    )

    if settings.CLIP_WARMUP_ENABLED:
        threading.Thread(
            target=_warmup_clip_model,
            name="clip-warmup",
            daemon=True,        # 主进程退出时不阻塞
        ).start()
        logger.info("CLIP 预热线程已启动（后台加载模型，不阻塞端口监听）")
    else:
        logger.info("CLIP 预热已禁用（CLIP_WARMUP_ENABLED=false），恢复懒加载")

    yield
    logger.info("正在关闭应用...")

# ---- 创建应用 ----
app = FastAPI(
    title="校园失物检索平台 API",
    description="基于加权融合相似度算法的校园失物检索系统",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# ---- CORS 配置（开发环境允许所有 localhost 端口） ----
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://localhost:\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # 滑动续期：新令牌通过响应头下发，必须显式暴露给浏览器 JS，否则前端读不到
    expose_headers=["X-Renewed-Token"],
)

# ---- 注册路由 ----
from .api.auth import router as auth_router
from .api.items import router as items_router
from .api.admin import router as admin_router
from .api.notifications import router as notifications_router
from .api.stats import router as stats_router
from .api.announcements import router as announcements_router
from .api.claims import router as claims_router
from .api.reports import router as reports_router
from .api.comments import router as comments_router
from .api.banners import router as banners_router
from .api.categories import router as categories_router

app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(items_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(notifications_router, prefix=settings.API_V1_STR)
app.include_router(stats_router, prefix=settings.API_V1_STR)
app.include_router(announcements_router, prefix=settings.API_V1_STR)
app.include_router(claims_router, prefix=settings.API_V1_STR)
app.include_router(reports_router, prefix=settings.API_V1_STR)
app.include_router(comments_router, prefix=settings.API_V1_STR)
app.include_router(banners_router, prefix=settings.API_V1_STR)
app.include_router(categories_router, prefix=settings.API_V1_STR)

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
        "message": f"校园失物检索平台 API v{settings.APP_VERSION}",
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