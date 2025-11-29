from .session import init_database
from .db_manager import (
    collect_and_save_daily_data,
    collect_and_save_exchange_rates,
    run_daily_task,
    run_daily_fx_task,
    get_daily_summary,
    get_price_history,
    check_data_integrity,
    is_data_exists,
    print_daily_summary,
    GoldCollectionResult,
    FxCollectionResult,
    CollectionResult,
    DailySummary,
)
from .fx_repository import (
    ExchangeRateRecord,
    upsert_exchange_rate,
    get_exchange_rate_by_date,
    get_latest_exchange_rates,
    is_exchange_rate_exists,
)


__all__ = [
    "init_database",
    # 黄金采集
    "collect_and_save_daily_data",
    "run_daily_task",
    "GoldCollectionResult",
    # 汇率采集
    "collect_and_save_exchange_rates",
    "run_daily_fx_task",
    "FxCollectionResult",
    # 查询函数
    "get_daily_summary",
    "get_price_history",
    "check_data_integrity",
    "is_data_exists",
    "print_daily_summary",
    # 类型（兼容）
    "CollectionResult",
    "DailySummary",
    # 汇率 Repository
    "ExchangeRateRecord",
    "upsert_exchange_rate",
    "get_exchange_rate_by_date",
    "get_latest_exchange_rates",
    "is_exchange_rate_exists",
]
