"""
汇率数据模型
记录人民币对各主要货币的每日汇率（中间价）
"""
from sqlalchemy import Table, Column, REAL, TEXT, DATE, DATETIME, func

from model.gold_price import metadata  # 复用同一个 metadata


# 表定义：daily_exchange_rates
daily_exchange_rates = Table(
    "daily_exchange_rates",
    metadata,
    Column("date", DATE, primary_key=True, comment="日期(YYYY-MM-DD)"),
    Column("usd_cny", REAL, comment="USD/CNY 中间价"),
    Column("jpy_cny", REAL, comment="100JPY/CNY 中间价"),  # 日元通常以100为单位报价
    Column("eur_cny", REAL, comment="EUR/CNY 中间价"),
    Column("source", TEXT, nullable=False, default="chinamoney", comment="数据来源: chinamoney, fallback"),
    Column("status", TEXT, nullable=False, default="valid", comment="数据状态: valid, partial"),
    Column("created_at", DATETIME, server_default=func.now(), comment="记录入库时间"),
)
