"""
数据库业务管理器
整合数据采集、校验和存储的业务逻辑层
"""
from typing import Optional, List, TypedDict
from datetime import date, datetime

from data_sources import fetch_lbma_price, fetch_sge_price, fetch_usd_cny_rate
from validator import validate_daily_data, calculate_theoretical_price
from database.repository import (
    GoldPriceRecord,
    upsert_record,
    get_record_by_date,
    get_latest_n_records,
)


# ======================
# 数据结构
# ======================
class CollectionResult(TypedDict):
    """采集任务执行结果"""
    success: bool                          # 是否成功入库
    date: str                              # 日期
    record: Optional[GoldPriceRecord]      # 入库的记录
    lbma_source: str                       # 数据来源标识
    sge_source: str                        # "sge_api" | "unavailable"
    fx_source: str                         # "chinamoney" | "fallback"
    validation_status: str                 # valid | suspicious_xxx
    error: Optional[str]                   # 错误信息


class DailySummary(TypedDict):
    """每日数据摘要"""
    date: str
    lbma_pm_usd: float
    sge_close_cny: Optional[float]
    usd_cny: float
    theoretical_cny_per_gram: float
    sge_premium_pct: Optional[float]       # SGE 溢价率
    status: str
    validation_notes: str


# ======================
# 核心业务函数
# ======================
def collect_and_save_daily_data(target_date: Optional[date] = None) -> CollectionResult:
    """
    执行每日数据采集任务
    
    流程:
    1. 采集 LBMA 价格（必须成功）
    2. 采集 USD/CNY 汇率（必须成功）
    3. 采集 SGE 价格（可选）
    4. 执行数据校验
    5. 组装记录并存储
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        CollectionResult: 采集结果详情
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    # 初始化结果
    result: CollectionResult = {
        "success": False,
        "date": date_str,
        "record": None,
        "lbma_source": "",
        "sge_source": "",
        "fx_source": "",
        "validation_status": "",
        "error": None,
    }
    
    # 1. 采集 LBMA 价格（必须成功）
    lbma_result = fetch_lbma_price(target_date)
    if not lbma_result["success"]:
        result["error"] = f"LBMA 采集失败: {lbma_result['error']}"
        return result
    
    lbma_price = lbma_result["price"]
    result["lbma_source"] = "goldapi"
    
    # 2. 采集 USD/CNY 汇率（必须成功）
    fx_result = fetch_usd_cny_rate(target_date)
    if not fx_result["success"]:
        result["error"] = f"汇率采集失败: {fx_result['error']}"
        return result
    
    usd_cny = fx_result["rate"]
    result["fx_source"] = "chinamoney"
    
    # 3. 采集 SGE 价格（可选）
    sge_result = fetch_sge_price(target_date)
    sge_price: Optional[float] = None
    sge_available = False
    
    if sge_result["success"] and sge_result.get("available", False):
        sge_price = sge_result["price"]
        sge_available = True
        result["sge_source"] = "sge_api"
    else:
        result["sge_source"] = "unavailable"
    
    # 4. 执行数据校验
    validation = validate_daily_data(
        lbma_price=lbma_price,
        usd_cny=usd_cny,
        sge_price=sge_price,
        date_str=date_str
    )
    
    result["validation_status"] = validation["status"]
    
    # 5. 组装记录
    record: GoldPriceRecord = {
        "date": date_str,
        "lbma_pm_usd": lbma_price,
        "sge_close_cny": sge_price,
        "usd_cny": usd_cny,
        "theoretical_cny_per_gram": validation["theoretical_cny_per_gram"],
        "sge_available": sge_available,
        "status": validation["status"],
        "validation_notes": validation["validation_notes"],
    }
    
    # 6. 存储记录（upsert 保证幂等）
    try:
        upsert_record(record)
        result["success"] = True
        result["record"] = record
    except Exception as e:
        result["error"] = f"数据库写入失败: {str(e)}"
    
    return result


def get_daily_summary(date_str: str) -> Optional[DailySummary]:
    """
    获取指定日期的数据摘要
    
    Args:
        date_str: 日期字符串 (YYYY-MM-DD)
    
    Returns:
        DailySummary 或 None（无数据时）
    """
    record = get_record_by_date(date_str)
    if record is None:
        return None
    
    # 计算 SGE 溢价率
    sge_premium_pct: Optional[float] = None
    if record["sge_close_cny"] is not None and record["theoretical_cny_per_gram"] > 0:
        sge_premium_pct = (
            (record["sge_close_cny"] / record["theoretical_cny_per_gram"]) - 1
        ) * 100
    
    return DailySummary(
        date=record["date"],
        lbma_pm_usd=record["lbma_pm_usd"],
        sge_close_cny=record["sge_close_cny"],
        usd_cny=record["usd_cny"],
        theoretical_cny_per_gram=record["theoretical_cny_per_gram"],
        sge_premium_pct=sge_premium_pct,
        status=record["status"],
        validation_notes=record["validation_notes"] or "",
    )


def get_price_history(days: int = 30) -> List[DailySummary]:
    """
    获取历史价格走势
    
    Args:
        days: 获取最近多少天的数据
    
    Returns:
        按日期倒序排列的摘要列表
    """
    records = get_latest_n_records(days)
    summaries: List[DailySummary] = []
    
    for record in records:
        sge_premium_pct: Optional[float] = None
        if record["sge_close_cny"] is not None and record["theoretical_cny_per_gram"] > 0:
            sge_premium_pct = (
                (record["sge_close_cny"] / record["theoretical_cny_per_gram"]) - 1
            ) * 100
        
        summaries.append(DailySummary(
            date=record["date"],
            lbma_pm_usd=record["lbma_pm_usd"],
            sge_close_cny=record["sge_close_cny"],
            usd_cny=record["usd_cny"],
            theoretical_cny_per_gram=record["theoretical_cny_per_gram"],
            sge_premium_pct=sge_premium_pct,
            status=record["status"],
            validation_notes=record["validation_notes"] or "",
        ))
    
    return summaries


def check_data_integrity(days: int = 30) -> dict:
    """
    检查数据完整性
    
    Args:
        days: 检查最近多少天
    
    Returns:
        {
            "total_records": int,
            "valid_count": int,
            "suspicious_count": int,
            "sge_available_count": int,
            "missing_dates": List[str],  # 缺失的交易日
            "suspicious_records": List[dict],  # 异常记录摘要
        }
    """
    records = get_latest_n_records(days)
    
    valid_count = 0
    suspicious_count = 0
    sge_available_count = 0
    suspicious_records = []
    
    for record in records:
        if record["status"] == "valid":
            valid_count += 1
        else:
            suspicious_count += 1
            suspicious_records.append({
                "date": record["date"],
                "status": record["status"],
                "notes": record["validation_notes"],
            })
        
        if record["sge_available"]:
            sge_available_count += 1
    
    # TODO: 计算缺失的交易日（需要交易日历）
    missing_dates: List[str] = []
    
    return {
        "total_records": len(records),
        "valid_count": valid_count,
        "suspicious_count": suspicious_count,
        "sge_available_count": sge_available_count,
        "missing_dates": missing_dates,
        "suspicious_records": suspicious_records,
    }


def is_data_exists(date_str: str) -> bool:
    """
    检查指定日期是否已有数据
    
    Args:
        date_str: 日期字符串 (YYYY-MM-DD)
    
    Returns:
        True 如果数据已存在
    """
    return get_record_by_date(date_str) is not None


# ======================
# 便捷函数
# ======================
def run_daily_task() -> CollectionResult:
    """
    运行每日采集任务（当天）
    便捷入口，供 main.py 或调度器调用
    """
    return collect_and_save_daily_data()


def print_daily_summary(date_str: Optional[str] = None) -> None:
    """
    打印每日数据摘要（用于调试/查看）
    """
    if date_str is None:
        date_str = date.today().isoformat()
    
    summary = get_daily_summary(date_str)
    if summary is None:
        print(f"❌ {date_str} 无数据")
        return
    
    print(f"\n📊 {summary['date']} 黄金价格数据")
    print("=" * 40)
    print(f"  LBMA 定盘价:    ${summary['lbma_pm_usd']:.2f}/盎司")
    print(f"  USD/CNY 汇率:   {summary['usd_cny']:.4f}")
    print(f"  理论进口金价:   ¥{summary['theoretical_cny_per_gram']:.2f}/克")
    
    if summary["sge_close_cny"] is not None:
        print(f"  SGE Au99.99:    ¥{summary['sge_close_cny']:.2f}/克")
        if summary["sge_premium_pct"] is not None:
            print(f"  SGE 溢价率:     {summary['sge_premium_pct']:+.2f}%")
    else:
        print(f"  SGE Au99.99:    无交易")
    
    print(f"  数据状态:       {summary['status']}")
    print("=" * 40)


if __name__ == "__main__":
    # 测试：执行当日采集
    print("开始执行每日采集任务...")
    result = run_daily_task()
    
    if result["success"]:
        print(f"✅ 采集成功: {result['date']}")
        print(f"   状态: {result['validation_status']}")
        print_daily_summary(result["date"])
    else:
        print(f"❌ 采集失败: {result['error']}")
