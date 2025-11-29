"""数据库会话管理
提供统一的数据库连接单例，避免重复创建连接
"""
import os
from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.pool import StaticPool
from config import get_config
from model import metadata


# ======================
# 全局单例 Engine
# ======================
_engine: Optional[Engine] = None
_initialized: bool = False


def get_database_url() -> str:
    """根据配置返回数据库 URL"""
    config = get_config()
    db_type = config["database"]["type"]
    
    if db_type == "sqlite":
        db_path = config["database"]["path"]
        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # SQLite URL 格式
        return f"sqlite:///{os.path.abspath(db_path)}"
    elif db_type == "mysql":
        # 未来扩展用
        cfg = config["database"]
        return f"mysql+pymysql://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def get_engine() -> Engine:
    """
    获取数据库引擎（单例模式）
    
    首次调用时创建引擎，后续调用返回同一实例。
    不会自动创建表，需要显式调用 init_database()。
    
    Returns:
        Engine: SQLAlchemy 引擎实例
    """
    global _engine
    
    if _engine is not None:
        return _engine
    
    db_url = get_database_url()
    
    if db_url.startswith("sqlite"):
        _engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False
        )
    else:
        _engine = create_engine(db_url, echo=False)
    
    return _engine


def init_database() -> Engine:
    """
    初始化数据库：创建表（如果不存在）
    
    此函数是幂等的，多次调用只会在首次时创建表并打印消息。
    
    Returns:
        Engine: 数据库引擎实例
    """
    global _initialized
    
    engine = get_engine()
    
    if not _initialized:
        # 创建所有表（幂等操作，已存在则跳过）
        metadata.create_all(engine)
        print(f"✅ 数据库初始化成功: {engine.url}")
        _initialized = True
    
    return engine


def close_engine() -> None:
    """
    关闭数据库连接（用于测试或程序退出时清理）
    """
    global _engine, _initialized
    
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _initialized = False
