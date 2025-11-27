import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 日志目录
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.log"

# 创建日志目录
if not LOG_DIR.exists():
    LOG_DIR.mkdir(exist_ok=True)

def get_logger(name: str = "gold_tracker") -> logging.Logger:
    """
    获取配置好的 logger
    """
    logger = logging.getLogger(name)
    
    # 如果已经配置过 handlers，直接返回（避免重复日志）
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    
    # 格式器
    formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 1. 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    # 2. 文件 Handler (每天轮转，保留 30 天)
    file_handler = TimedRotatingFileHandler(
        filename=LOG_FILE,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    return logger

# 默认导出
logger = get_logger()
