# app/config.py
from pydantic_settings import BaseSettings
from typing import Optional, Set, List


class Settings(BaseSettings):
    APP_NAME: str = "校园失物检索平台"
    API_V1_STR: str = "/api"

    # 安全配置
    SECRET_KEY: str
    JWT_EXPIRATION: int = 7

    # 数据库
    DATABASE: str = "lost_found.db"

    # 上传配置
    UPLOAD_FOLDER: str = "uploads"
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS: Set[str] = {"png", "jpg", "jpeg", "gif", "webp"}

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174"]

    # 日志
    LOG_LEVEL: str = "INFO"

    # 匹配阈值（五阶段优化分层）
    MATCH_THRESHOLD_MANUAL: float = 0.20    # 手动匹配：宽松，用户自己筛选
    MATCH_THRESHOLD_AUTO: float = 0.65      # 自动匹配通知：严格
    MATCH_THRESHOLD_EMAIL: float = 0.75     # 邮件通知：最严格，仅极高置信度
    MAX_AUTO_MATCH_NOTIFICATIONS: int = 3

    # 前端基础URL（用于邮件链接）
    BASE_URL: str = "http://localhost:5173"

    # 邮件配置
    MAIL_SERVER: str = "smtp.qq.com"
    MAIL_PORT: int = 465
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()