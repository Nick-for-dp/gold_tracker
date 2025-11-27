from sqlalchemy import Table, Column, MetaData, REAL, TEXT, BOOLEAN, DATE, DATETIME, func


# 全局 MetaData 对象（用于 create_all）
metadata = MetaData()

# 表定义：daily_gold_prices
daily_gold_prices = Table(
    "daily_gold_prices",
    metadata,
    Column("date", DATE, primary_key=True, comment="日期(YYYY-MM-DD)"),
    Column("lbma_pm_usd", REAL, nullable=False, comment="LBMA 下午定盘价(美元/盎司)"),
    Column("sge_close_cny", REAL, comment="SGE Au99.99 收盘价（人民币/克）"),
    Column("usd_cny", REAL, nullable=False, comment="USD/CNY 中间价"),
    Column("theoretical_cny_per_gram", REAL, nullable=False, comment="理论进口金价 = (LBMA * 汇率) / 31.1035"),
    Column("sge_available", BOOLEAN, nullable=False, comment="当日 SGE 是否交易(0/1)"),
    Column("status", TEXT, nullable=False, comment="数据状态: valid, suspicious_lbma, ..."),
    Column("validation_notes", TEXT, comment="校验详情说明"),
    Column("created_at", DATETIME, server_default=func.now(), comment="记录入库时间"),
)
