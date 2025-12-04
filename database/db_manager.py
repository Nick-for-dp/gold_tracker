"""
数据库业务管理器
整合数据采集、校验和存储的业务逻辑层
"""
from typing import Optional, List, TypedDict
from datetime import date, datetime
from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError

from data_sources import fetch_lbma_price, fetch_sge_price, fetch_usd_cny_rate, fetch_multi_currency_rates
from utils.logger import logger
from validator import validate_daily_data, calculate_theoretical_price
from database.repository import (
    GoldPriceRecord,
    upsert_record,
    get_record_by_date,
    get_latest_n_records,
    get_previous_fx_rate,
)
from database.fx_repository import (
    ExchangeRateRecord,
    upsert_exchange_rate,
    get_exchange_rate_by_date,
    get_latest_exchange_rates,
)


# ======================
# 数据结构
# ======================
class GoldCollectionResult(TypedDict):
    """黄金价格采集任务执行结果"""
    success: bool                          # 是否成功入库
    date: str                              # 日期
    record: Optional[GoldPriceRecord]      # 入库的记录
    lbma_source: str                       # 数据来源标识
    sge_source: str                        # "sge_api" | "unavailable"
    fx_source: str                         # "chinamoney" | "fallback"
    validation_status: str                 # valid | suspicious_xxx
    error: Optional[str]                   # 错误信息


class FxCollectionResult(TypedDict):
    """汇率采集任务执行结果"""
    success: bool                          # 是否成功入库
    date: str                              # 日期
    record: Optional[ExchangeRateRecord]   # 入库的记录
    source: str                            # 数据来源
    currencies_collected: List[str]        # 成功采集的货币对
    error: Optional[str]                   # 错误信息


# 保持向后兼容的别名
CollectionResult = GoldCollectionResult


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
def collect_and_save_daily_data(target_date: Optional[date] = None) -> GoldCollectionResult:
    """
    执行每日黄金价格采集任务
    
    流程:
    1. 采集 LBMA 价格（必须成功）
    2. 采集 USD/CNY 汇率（必须成功）
    3. 采集 SGE 价格（可选）
    4. 执行数据校验
    5. 组装记录并存储
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        GoldCollectionResult: 采集结果详情
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    logger.info(f"[黄金采集] 开始采集 {date_str} 的黄金价格数据")
    
    # 初始化结果
    result: GoldCollectionResult = {
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
    try:
        lbma_result = fetch_lbma_price(target_date)
    except RequestException as e:
        error_msg = f"LBMA 网络请求失败: {str(e)}"
        logger.error(f"[黄金采集] {error_msg}")
        result["error"] = error_msg
        return result
    except Exception as e:
        error_msg = f"LBMA 数据解析失败: {str(e)}"
        logger.error(f"[黄金采集] {error_msg}", exc_info=True)
        result["error"] = error_msg
        return result
    
    if not lbma_result["success"]:
        error_msg = f"LBMA 采集失败: {lbma_result['error']}"
        logger.error(f"[黄金采集] {error_msg}")
        result["error"] = error_msg
        return result
    
    lbma_price = lbma_result["price"]
    result["lbma_source"] = "goldapi"
    logger.info(f"[黄金采集] LBMA 定盘价: ${lbma_price:.2f}/盎司")
    
    # 2. 采集 USD/CNY 汇率（必须成功，否则回退到最近一个交易日）
    usd_cny: Optional[float] = None
    fx_source = ""
    
    try:
        fx_result = fetch_usd_cny_rate(target_date)
        if fx_result["success"]:
            usd_cny = fx_result["rate"]
            fx_source = "chinamoney"
            logger.info(f"[黄金采集] USD/CNY 汇率: {usd_cny:.4f}")
        else:
            logger.warning(f"[黄金采集] 当日汇率获取失败: {fx_result['error']}")
    except RequestException as e:
        logger.warning(f"[黄金采集] USD/CNY 网络请求失败: {str(e)}")
    except Exception as e:
        logger.warning(f"[黄金采集] USD/CNY 数据解析失败: {str(e)}")
    
    # 如果当日汇率获取失败，回退到最近一个交易日的汇率
    if usd_cny is None:
        logger.info(f"[黄金采集] 尝试使用最近一个交易日的汇率...")
        try:
            previous_rate = get_previous_fx_rate(date_str)
            if previous_rate is not None:
                usd_cny = previous_rate
                fx_source = "previous_day"
                logger.info(f"[黄金采集] 使用前一交易日汇率: {usd_cny:.4f}")
            else:
                error_msg = "汇率采集失败，且无历史数据可回退"
                logger.error(f"[黄金采集] {error_msg}")
                result["error"] = error_msg
                return result
        except Exception as e:
            error_msg = f"查询历史汇率失败: {str(e)}"
            logger.error(f"[黄金采集] {error_msg}")
            result["error"] = error_msg
            return result
    
    result["fx_source"] = fx_source
    
    # 3. 采集 SGE 价格（可选）
    sge_price: Optional[float] = None
    sge_available = False
    
    try:
        sge_result = fetch_sge_price(target_date)
        if sge_result["success"] and sge_result.get("available", False):
            sge_price = sge_result["price"]
            sge_available = True
            result["sge_source"] = "sge_api"
            logger.info(f"[黄金采集] SGE Au99.99: ¥{sge_price:.2f}/克")
        else:
            result["sge_source"] = "unavailable"
            logger.info(f"[黄金采集] SGE 无交易数据")
    except Exception as e:
        result["sge_source"] = "unavailable"
        logger.warning(f"[黄金采集] SGE 采集异常（不影响主流程）: {str(e)}")
    
    # 4. 执行数据校验
    validation = validate_daily_data(
        lbma_price=lbma_price,
        usd_cny=usd_cny,
        sge_price=sge_price,
        date_str=date_str
    )
    result["validation_status"] = validation["status"]
    logger.info(f"[黄金采集] 理论进口金价: ¥{validation['theoretical_cny_per_gram']:.2f}/克")
    logger.info(f"[黄金采集] 数据校验状态: {validation['status']}")
    
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
        logger.info(f"[黄金采集] 数据已存入数据库")
    except SQLAlchemyError as e:
        error_msg = f"数据库写入失败: {str(e)}"
        logger.error(f"[黄金采集] {error_msg}", exc_info=True)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"[黄金采集] {error_msg}", exc_info=True)
        result["error"] = error_msg
    
    return result


def collect_and_save_exchange_rates(target_date: Optional[date] = None) -> FxCollectionResult:
    """
    执行每日汇率采集任务（独立任务）
    
    采集 USD/CNY、JPY/CNY、EUR/CNY 汇率并存入 daily_exchange_rates 表。
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        FxCollectionResult: 采集结果详情
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    logger.info(f"[汇率采集] 开始采集 {date_str} 的汇率数据")
    
    result: FxCollectionResult = {
        "success": False,
        "date": date_str,
        "record": None,
        "source": "",
        "currencies_collected": [],
        "error": None,
    }
    
    try:
        fx_result = fetch_multi_currency_rates(target_date)
        
        if not fx_result["success"]:
            error_msg = f"汇率采集失败: {'; '.join(fx_result.get('errors', []))}"
            logger.error(f"[汇率采集] {error_msg}")
            result["error"] = error_msg
            return result
        
        rates = fx_result["rates"]
        result["source"] = fx_result["source"]
        
        # 记录成功采集的货币对和汇率值
        collected = []
        collected_details = []
        for key in ["usd_cny", "jpy_cny", "eur_cny"]:
            val = rates.get(key)
            if val is not None:
                currency_pair = key.upper().replace("_", "/")
                collected.append(currency_pair)
                collected_details.append(f"{currency_pair}={val:.4f}")
                
        result["currencies_collected"] = collected
        logger.info(f"[汇率采集] 成功采集: {', '.join(collected_details)} (来源: {fx_result['source']})")
        
        # 判断状态
        status = "valid" if not fx_result.get("errors") else "partial"
        
        fx_record: ExchangeRateRecord = {
            "date": date_str,
            "usd_cny": rates.get("usd_cny"),
            "jpy_cny": rates.get("jpy_cny"),
            "eur_cny": rates.get("eur_cny"),
            "source": fx_result["source"],
            "status": status,
        }
        
        upsert_exchange_rate(fx_record)
        logger.info(f"[汇率采集] 数据已存入数据库")
        
        result["success"] = True
        result["record"] = fx_record
        
    except Exception as e:
        error_msg = f"汇率采集异常: {str(e)}"
        logger.error(f"[汇率采集] {error_msg}", exc_info=True)
        result["error"] = error_msg
    
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
def run_daily_task() -> GoldCollectionResult:
    """
    运行每日黄金采集任务（当天）
    便捷入口，供 main.py 或调度器调用
    """
    return collect_and_save_daily_data()


def run_daily_fx_task() -> FxCollectionResult:
    """
    运行每日汇率采集任务（当天）
    便捷入口，供调度器调用
    """
    return collect_and_save_exchange_rates()


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
