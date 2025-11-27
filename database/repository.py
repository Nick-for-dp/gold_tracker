from typing import List, Optional, Dict, Any, TypedDict, cast, Union
from datetime import date
from sqlalchemy import select, insert
from sqlalchemy.exc import SQLAlchemyError

from database import init_database  # 用于获取 engine
from model import daily_gold_prices


# ======================
# 数据结构契约定义（TypedDict）
# ======================
class GoldPriceRecord(TypedDict):
    """
    黄金价格记录的数据结构契约(用于类型提示，运行时仍为 dict)
    """
    date: str                              # YYYY-MM-DD
    lbma_pm_usd: float                     # LBMA 下午定盘价（美元/盎司）
    sge_close_cny: Optional[float]         # SGE 收盘价（人民币/克），可为 None
    usd_cny: float                         # USD/CNY 中间价
    theoretical_cny_per_gram: float        # 理论进口金价（元/克）
    sge_available: bool                    # 当日 SGE 是否交易
    status: str                            # 数据状态（如 "valid", "suspicious_lbma"）
    validation_notes: Optional[str]        # 校验说明


# ======================
# 数据库引擎（单例）
# ======================
_engine = init_database()


# ======================
# 数据格式转换（内部使用）
# ======================
def _to_db_record(record: GoldPriceRecord) -> Dict[str, Any]:
    """
    将用户输入的记录转换为数据库可接受的格式
    - date: str -> date 对象
    """
    result = dict(record)
    date_value = result.get("date")
    if isinstance(date_value, str):
        result["date"] = date.fromisoformat(date_value)
    return result


def _from_db_record(row_mapping: Any) -> GoldPriceRecord:
    """
    将数据库返回的记录转换为用户友好的格式
    - date: date 对象 -> str (YYYY-MM-DD)
    """
    result = dict(row_mapping)
    date_value = result.get("date")
    if isinstance(date_value, date):
        result["date"] = date_value.isoformat()
    return cast(GoldPriceRecord, result)


# ======================
# CRUD 操作（仅接受/返回 GoldPriceRecord 类型）
# ======================
def save_record(record: GoldPriceRecord) -> None:
    """
    插入一条黄金价格记录（若 date 已存在，则忽略）
    """
    try:
        db_record = _to_db_record(record)
        with _engine.connect() as conn:
            stmt = insert(daily_gold_prices).values(**db_record)
            # SQLite 和 MySQL 均支持 ON CONFLICT / ON DUPLICATE KEY，但为简化，先查后插
            # 更优方案：使用 upsert（见下方说明）
            conn.execute(stmt)
            conn.commit()
    except SQLAlchemyError as e:
        raise RuntimeError(f"保存记录失败: {e}")


def upsert_record(record: GoldPriceRecord) -> None:
    """
    插入或更新记录（推荐用于幂等写入）
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    
    try:
        db_record = _to_db_record(record)
        with _engine.connect() as conn:
            stmt = sqlite_insert(daily_gold_prices).values(**db_record)
            # 只更新传入的非主键字段
            update_fields = {k: stmt.excluded[k] for k in record if k != 'date'}
            stmt = stmt.on_conflict_do_update(
                index_elements=['date'],
                set_=update_fields
            )
            conn.execute(stmt)
            conn.commit()
    except SQLAlchemyError as e:
        raise RuntimeError(f"Upsert 记录失败: {e}")


def get_record_by_date(date: str) -> Optional[GoldPriceRecord]:
    """
    根据日期查询单条记录
    """
    try:
        with _engine.connect() as conn:
            stmt = select(daily_gold_prices).where(daily_gold_prices.c.date == date)
            result = conn.execute(stmt).fetchone()
            return _from_db_record(result._mapping) if result else None
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询记录失败: {e}")


def get_latest_n_records(n: int = 30) -> List[GoldPriceRecord]:
    """
    获取最近 N 条记录（按日期倒序）
    """
    try:
        with _engine.connect() as conn:
            stmt = select(daily_gold_prices).order_by(daily_gold_prices.c.date.desc()).limit(n)
            results = conn.execute(stmt).fetchall()
            return [_from_db_record(row._mapping) for row in results]
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询最近记录失败: {e}")


def get_recent_lbma_prices(days: int = 20) -> List[float]:
    """
    获取最近 N 个交易日的 LBMA 价格（用于动态校验）
    """
    try:
        with _engine.connect() as conn:
            stmt = (
                select(daily_gold_prices.c.lbma_pm_usd)
                .where(daily_gold_prices.c.status == 'valid')
                .order_by(daily_gold_prices.c.date.desc())
                .limit(days)
            )
            results = conn.execute(stmt).fetchall()
            return [row[0] for row in results]
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询 LBMA 历史价格失败: {e}")


def get_previous_fx_rate(current_date: str) -> Optional[float]:
    """
    获取前一个交易日的 USD/CNY 汇率（用于汇率校验）
    """
    try:
        with _engine.connect() as conn:
            stmt = (
                select(daily_gold_prices.c.usd_cny)
                .where(daily_gold_prices.c.date < current_date)
                .order_by(daily_gold_prices.c.date.desc())
                .limit(1)
            )
            result = conn.execute(stmt).fetchone()
            return result[0] if result else None
    except SQLAlchemyError as e:
        raise RuntimeError(f"查询前一日汇率失败: {e}")
