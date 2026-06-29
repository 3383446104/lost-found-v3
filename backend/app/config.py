# app/config.py
from pydantic_settings import BaseSettings
from typing import Optional, Set, List


class Settings(BaseSettings):
    APP_NAME: str = "校园失物智能寻回系统"
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

    # 匹配阈值
    MATCH_THRESHOLD: float = 0.3
    AUTO_MATCH_THRESHOLD: float = 0.6

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