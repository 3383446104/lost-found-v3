# app/logger.py
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logger(name: str = "app") -> logging.Logger:
    """配置并返回日志记录器，默认日志级别为 INFO"""
    # 尝试从配置读取日志级别，若失败则默认 INFO
    try:
        from .config import settings
        log_level_str = getattr(settings, "LOG_LEVEL", "INFO")
    except (ImportError, AttributeError):
        log_level_str = "INFO"

    # 将字符串转为 logging 常量，若无效则降级为 INFO
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # 避免重复添加 handler（若需重新配置可先清空）
    if logger.handlers:
        return logger

    # 控制台 Handler（输出到 stdout，指定 UTF-8 编码）
    import io
    console_handler = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'))
    console_handler.setLevel(log_level)
    console_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # 文件 Handler（自动轮转，指定 UTF-8 编码）
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)  # 安全创建目录
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"  # 避免编码问题
    )
    file_handler.setLevel(log_level)
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger

# 创建全局 logger 实例（您也可以在应用入口处调用 setup_logger() 来延迟初始化）
logger = setup_logger()