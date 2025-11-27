import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import get_config
from utils.logger import logger

# 备份目录
BACKUP_DIR = Path("backups")

# 确保备份目录存在
if not BACKUP_DIR.exists():
    BACKUP_DIR.mkdir(exist_ok=True)


def backup_database(max_backups: int = 10) -> Optional[str]:
    """
    备份数据库文件
    
    Args:
        max_backups: 保留的最大备份数量
        
    Returns:
        备份文件路径 (str) 或 None (失败时)
    """
    config = get_config()
    db_path = Path(config["database"]["path"])
    
    if not db_path.exists():
        logger.error(f"数据库文件不存在: {db_path}")
        return None
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"gold_tracker_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_filename
    
    try:
        # 复制文件
        shutil.copy2(db_path, backup_path)
        logger.info(f"数据库已备份: {backup_path} (大小: {backup_path.stat().st_size / 1024:.2f} KB)")
        
        # 清理旧备份
        _cleanup_old_backups(max_backups)
        
        return str(backup_path)
        
    except Exception as e:
        logger.error(f"备份失败: {e}", exc_info=True)
        return None


def _cleanup_old_backups(keep_count: int) -> None:
    """
    清理旧备份，只保留最近的 N 个
    """
    try:
        # 获取所有备份文件，按修改时间倒序排列
        backups = sorted(
            BACKUP_DIR.glob("gold_tracker_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        if len(backups) > keep_count:
            to_remove = backups[keep_count:]
            for p in to_remove:
                p.unlink()
                logger.info(f"已删除旧备份: {p.name}")
                
    except Exception as e:
        logger.warning(f"清理旧备份时出错: {e}")


if __name__ == "__main__":
    # 测试代码
    print("开始备份测试...")
    path = backup_database(max_backups=3)
    if path:
        print(f"✅ 备份成功: {path}")
    else:
        print("❌ 备份失败")
