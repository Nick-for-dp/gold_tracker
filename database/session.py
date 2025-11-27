import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from config import get_config
from model import metadata


def get_database_url():
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
        # 未来扩展用（当前可注释）
        cfg = config["database"]
        return f"mysql+pymysql://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def init_database():
    """
    初始化数据库：创建表（如果不存在）
    """
    db_url = get_database_url()
    
    if db_url.startswith("sqlite"):
        # SQLite 特殊配置
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,  # SQLite 单文件，无需连接池
            echo=False  # 生产环境关闭 SQL 日志
        )
    else:
        # MySQL 等（未来用）
        engine = create_engine(db_url, echo=False)
    
    # 创建所有表（幂等操作，已存在则跳过）
    metadata.create_all(engine)
    print(f"✅ 数据库初始化成功: {db_url}")
    return engine
