import os
import yaml
from pathlib import Path


# 配置文件默认路径（相对于项目根目录）
CONFIG_FILE = "config.yaml"
DEFAULT_CONFIG = {
    "database": {
        "type": "sqlite",
        "path": "data/gold_tracker.db"
    },
    "validation": {
        "lbma_window_days": 20,
        "lbma_sigma_threshold": 3.0,
        "sge_theoretical_low": 0.95,
        "sge_theoretical_high": 1.12,
        "fx_daily_change_limit": 0.02
    }
}


_config_cache = None


def get_config():
    """
    获取全局配置（单例模式，避免重复读取文件）
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = Path(CONFIG_FILE)
    
    if not config_path.exists():
        raise FileNotFoundError(
            f"配置文件未找到: {config_path.absolute()}\n"
            f"请复制 config.example.yaml 为 config.yaml 并填写必要参数。"
        )
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        
        # 合并默认配置与用户配置（用户配置优先）
        config = _deep_merge(DEFAULT_CONFIG, user_config)
                    
        _config_cache = config
        return _config_cache
    
    except yaml.YAMLError as e:
        raise ValueError(f"配置文件格式错误 ({config_path}): {e}")
    except Exception as e:
        raise RuntimeError(f"加载配置失败: {e}")


def _deep_merge(default, override):
    """
    递归合并两个字典(override 覆盖 default)
    """
    # 若 override 为 None 或非字典，保留 default
    if override is None:
        return default
    if not isinstance(default, dict) or not isinstance(override, dict):
        return override
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
