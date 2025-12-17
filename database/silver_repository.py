"""
白银价格数据仓库
"""
from typing import List, Optional, Dict, Any, TypedDict, cast
from datetime import date
from sqlalchemy import select, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from database import init_database
from model import daily_silver_prices


# ======================
# 数据结构契约定义（TypedDict）
# ======================
class SilverPriceRecord(TypedDict):
    """白银价格记录的数据结构契约"""
    date: str                              # YYYY-MM-DD
    lbma_pm_usd: float                     # LBMA 白银定盘价（美元/盎司）
    sge_close_cny: Optional[float]         # SGE Ag99.99 收盘价（人民币/克），可为 None
    usd_cny: float                         # USD/CNY 中间价
    theoretical_cny_per_gram: float        # 理论进口银价（元/克）
    sge_available: bool                    # 当日 SGE 是否交易
    status: str                            # 数据状态
    validation_notes: Optional[str]        # 校验说明


# ======================
# 数据库引擎（单例）
# ======================
_engine = init_database()


# ======================
# 数据格式转换（内部使用）
# ======================
def _to_db_record(record: SilverPriceRecord) -> Dict[str, Any]:
    """将用户输入的记录转换为数据库可接受的格式"""
    result = dict(record)
    date_value = result.get("date")
    if isinstance(date_value, str):
        result["date"] = date.fromisoformat(date_value)
    return result


def _from_db_record(row_mapping: Any) -> SilverPriceRecord:
    """将数据库返回的记录转换为用户友好的格式"""
    result = dict(row_mapping)
    date_value = result.get("date")
    if isinstance(date_value, date):
        result["date"] = date_value.isoformat()
    return cast(SilverPriceRecord, result)



# ======================
# CRUD 操作
# ======================
def upsert_silver_record(record: SilverPriceRecord) -> None:
    """插入或更新白银价格记录"""
    try:
        db_record = _to_db_record(record)
        with _engine.connect() as conn:
            stmt = sqlite_insert(daily_silver_prices).values(**db_record)
            update_fields = {k: stmt.excluded[k] for k in record if k != 'date'}
            stmt = stmt.on_conflict_do_update(
                index_elements=['date'],
                set_=update_fields
            )
            conn.execute(stmt)
            conn.commit()
    except SQLAlchemyError as e:
        raise RuntimeError(f"Upsert 白银记录失败: {e}")


def get_silver_record_by_date(date_str: str) -> Optional[SilverPriceRecord]:
    """根据日期查询单条白银记录"""
    try:
        with _engine.connect() as conn:
            stmt = select(daily_silver_prices).where(daily_silver_prices.c.date == date_str)
            result = conn.execute(stmt).fetchone()
            return _from_db_record(result._mapping) if result else None
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询白银记录失败: {e}")


def get_latest_silver_records(n: int = 30) -> List[SilverPriceRecord]:
    """获取最近 N 条白银记录（按日期倒序）"""
    try:
        with _engine.connect() as conn:
            stmt = select(daily_silver_prices).order_by(daily_silver_prices.c.date.desc()).limit(n)
            results = conn.execute(stmt).fetchall()
            return [_from_db_record(row._mapping) for row in results]
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询最近白银记录失败: {e}")


def get_recent_silver_lbma_prices(days: int = 20) -> List[float]:
    """获取最近 N 个交易日的白银 LBMA 价格（用于动态校验）"""
    try:
        with _engine.connect() as conn:
            stmt = (
                select(daily_silver_prices.c.lbma_pm_usd)
                .where(daily_silver_prices.c.status == 'valid')
                .order_by(daily_silver_prices.c.date.desc())
                .limit(days)
            )
            results = conn.execute(stmt).fetchall()
            return [row[0] for row in results]
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询白银 LBMA 历史价格失败: {e}")


def is_silver_data_exists(date_str: str) -> bool:
    """检查指定日期是否已有白银数据"""
    return get_silver_record_by_date(date_str) is not None
