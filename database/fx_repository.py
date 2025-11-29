"""
汇率数据存储层
提供汇率记录的 CRUD 操作
"""
from typing import Optional, Dict, Any, TypedDict, List, cast
from datetime import date
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from database import init_database
from model import daily_exchange_rates


# ======================
# 数据结构契约定义（TypedDict）
# ======================
class ExchangeRateRecord(TypedDict):
    """汇率记录的数据结构契约"""
    date: str                              # YYYY-MM-DD
    usd_cny: Optional[float]               # USD/CNY 中间价
    jpy_cny: Optional[float]               # 100JPY/CNY 中间价
    eur_cny: Optional[float]               # EUR/CNY 中间价
    source: str                            # 数据来源
    status: str                            # 数据状态: valid, partial


# ======================
# 数据库引擎（单例）
# ======================
_engine = init_database()


# ======================
# 数据格式转换（内部使用）
# ======================
def _to_db_record(record: ExchangeRateRecord) -> Dict[str, Any]:
    """将用户输入的记录转换为数据库可接受的格式"""
    result = dict(record)
    date_value = result.get("date")
    if isinstance(date_value, str):
        result["date"] = date.fromisoformat(date_value)
    return result


def _from_db_record(row_mapping: Any) -> ExchangeRateRecord:
    """将数据库返回的记录转换为用户友好的格式"""
    result = dict(row_mapping)
    date_value = result.get("date")
    if isinstance(date_value, date):
        result["date"] = date_value.isoformat()
    return cast(ExchangeRateRecord, result)


# ======================
# CRUD 操作
# ======================
def upsert_exchange_rate(record: ExchangeRateRecord) -> None:
    """
    插入或更新汇率记录（推荐用于幂等写入）
    """
    try:
        db_record = _to_db_record(record)
        with _engine.connect() as conn:
            stmt = sqlite_insert(daily_exchange_rates).values(**db_record)
            # 只更新传入的非主键字段
            update_fields = {k: stmt.excluded[k] for k in record if k != 'date'}
            stmt = stmt.on_conflict_do_update(
                index_elements=['date'],
                set_=update_fields
            )
            conn.execute(stmt)
            conn.commit()
    except SQLAlchemyError as e:
        raise RuntimeError(f"汇率记录写入失败: {e}")


def get_exchange_rate_by_date(date_str: str) -> Optional[ExchangeRateRecord]:
    """根据日期查询单条汇率记录"""
    try:
        with _engine.connect() as conn:
            stmt = select(daily_exchange_rates).where(
                daily_exchange_rates.c.date == date_str
            )
            result = conn.execute(stmt).fetchone()
            return _from_db_record(result._mapping) if result else None
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询汇率失败: {e}")


def get_latest_exchange_rates(n: int = 30) -> List[ExchangeRateRecord]:
    """获取最近 N 条汇率记录（按日期倒序）"""
    try:
        with _engine.connect() as conn:
            stmt = (
                select(daily_exchange_rates)
                .order_by(daily_exchange_rates.c.date.desc())
                .limit(n)
            )
            results = conn.execute(stmt).fetchall()
            return [_from_db_record(row._mapping) for row in results]
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询汇率历史失败: {e}")


def is_exchange_rate_exists(date_str: str) -> bool:
    """检查指定日期是否已有汇率数据"""
    return get_exchange_rate_by_date(date_str) is not None
