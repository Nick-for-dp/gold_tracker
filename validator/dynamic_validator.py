"""
动态数据校验器
对采集的黄金价格数据进行自适应校验
"""
import statistics
from typing import Optional, List, Tuple, TypedDict
from dataclasses import dataclass

from config import get_config
from database.repository import get_recent_lbma_prices, get_previous_fx_rate


# ======================
# 常量定义
# ======================
TROY_OUNCE_TO_GRAM = 31.1035  # 金衡盎司转克


# ======================
# 数据结构
# ======================
class ValidationResult(TypedDict):
    """校验结果"""
    status: str                    # valid, suspicious_lbma, suspicious_sge, suspicious_fx
    validation_notes: str          # 校验详情说明
    theoretical_cny_per_gram: float  # 理论进口金价（元/克）


@dataclass
class ValidationContext:
    """校验上下文，封装配置参数"""
    lbma_window_days: int
    lbma_sigma_threshold: float
    sge_theoretical_low: float
    sge_theoretical_high: float
    fx_daily_change_limit: float
    
    @classmethod
    def from_config(cls) -> "ValidationContext":
        """从配置文件加载校验参数"""
        config = get_config()
        validation = config["validation"]
        return cls(
            lbma_window_days=validation["lbma_window_days"],
            lbma_sigma_threshold=validation["lbma_sigma_threshold"],
            sge_theoretical_low=validation["sge_theoretical_low"],
            sge_theoretical_high=validation["sge_theoretical_high"],
            fx_daily_change_limit=validation["fx_daily_change_limit"],
        )


# ======================
# 核心校验函数
# ======================
def validate_daily_data(
    lbma_price: float,
    usd_cny: float,
    sge_price: Optional[float],
    date_str: str
) -> ValidationResult:
    """
    对当日采集数据执行动态校验
    
    Args:
        lbma_price: LBMA 下午定盘价（美元/盎司）
        usd_cny: USD/CNY 中间价
        sge_price: SGE Au99.99 收盘价（人民币/克），可为 None
        date_str: 日期字符串 (YYYY-MM-DD)
    
    Returns:
        ValidationResult: 包含 status, validation_notes, theoretical_cny_per_gram
    """
    ctx = ValidationContext.from_config()
    notes: List[str] = []
    status = "valid"
    
    # 1. 计算理论进口金价
    theoretical_price = calculate_theoretical_price(lbma_price, usd_cny)
    
    # 2. LBMA 价格校验
    lbma_valid, lbma_note = _validate_lbma_price(lbma_price, ctx)
    notes.append(f"[LBMA] {lbma_note}")
    if not lbma_valid:
        status = "suspicious_lbma"
    
    # 3. 汇率校验
    fx_valid, fx_note = _validate_fx_rate(usd_cny, date_str, ctx)
    notes.append(f"[汇率] {fx_note}")
    if not fx_valid and status == "valid":
        status = "suspicious_fx"
    
    # 4. SGE 价格校验（仅当 SGE 有数据时）
    if sge_price is not None:
        sge_valid, sge_note = _validate_sge_price(sge_price, theoretical_price, ctx)
        notes.append(f"[SGE] {sge_note}")
        if not sge_valid and status == "valid":
            status = "suspicious_sge"
    else:
        notes.append("[SGE] 当日无交易数据，跳过校验")
    
    return ValidationResult(
        status=status,
        validation_notes="; ".join(notes),
        theoretical_cny_per_gram=theoretical_price
    )


# ======================
# 计算函数
# ======================
def calculate_theoretical_price(lbma_usd: float, usd_cny: float) -> float:
    """
    计算理论进口金价（元/克）
    
    公式: (LBMA美元价 × 汇率) / 31.1035
    """
    return (lbma_usd * usd_cny) / TROY_OUNCE_TO_GRAM


# ======================
# 单项校验函数（内部使用）
# ======================
def _validate_lbma_price(
    current_price: float,
    ctx: ValidationContext
) -> Tuple[bool, str]:
    """
    LBMA 价格校验：基于历史数据的 μ ± 3σ 规则
    
    Returns:
        (is_valid, note)
    """
    # 获取历史数据
    history = get_recent_lbma_prices(ctx.lbma_window_days)
    
    # 冷启动处理
    if len(history) == 0:
        return True, "首条数据，跳过校验"
    
    mean = statistics.mean(history)
    
    if len(history) == 1:
        # 仅1条数据，无法计算标准差，使用 ±10% 阈值
        threshold = mean * 0.10
        lower, upper = mean - threshold, mean + threshold
        is_valid = lower <= current_price <= upper
        return is_valid, f"样本仅1条，±10%阈值: [{lower:.2f}, {upper:.2f}], 当前={current_price:.2f}"
    
    # 正常校验
    stdev = statistics.stdev(history)
    sigma = ctx.lbma_sigma_threshold
    lower = mean - sigma * stdev
    upper = mean + sigma * stdev
    is_valid = lower <= current_price <= upper
    
    # 构建说明
    sample_note = "" if len(history) >= ctx.lbma_window_days else f"样本不足({len(history)}条), "
    return is_valid, f"{sample_note}μ={mean:.2f}, σ={stdev:.2f}, 范围=[{lower:.2f}, {upper:.2f}], 当前={current_price:.2f}"


def _validate_sge_price(
    sge_price: float,
    theoretical_price: float,
    ctx: ValidationContext
) -> Tuple[bool, str]:
    """
    SGE 价格校验：与理论进口金价对比
    
    规则: SGE 价格应在理论价的 [95%, 112%] 区间内
    
    Returns:
        (is_valid, note)
    """
    lower = theoretical_price * ctx.sge_theoretical_low
    upper = theoretical_price * ctx.sge_theoretical_high
    is_valid = lower <= sge_price <= upper
    
    ratio = sge_price / theoretical_price if theoretical_price > 0 else 0
    ratio_pct = ratio * 100
    
    return is_valid, (
        f"理论价={theoretical_price:.2f}, "
        f"区间=[{lower:.2f}, {upper:.2f}], "
        f"实际={sge_price:.2f}, "
        f"溢价率={ratio_pct:.1f}%"
    )


def _validate_fx_rate(
    current_rate: float,
    date_str: str,
    ctx: ValidationContext
) -> Tuple[bool, str]:
    """
    汇率校验：单日变动不超过 ±2%
    
    Returns:
        (is_valid, note)
    """
    prev_rate = get_previous_fx_rate(date_str)
    
    # 冷启动处理
    if prev_rate is None:
        return True, "无历史汇率数据，跳过校验"
    
    change = (current_rate - prev_rate) / prev_rate
    change_pct = change * 100
    limit_pct = ctx.fx_daily_change_limit * 100
    
    is_valid = abs(change) <= ctx.fx_daily_change_limit
    
    return is_valid, (
        f"前日={prev_rate:.4f}, "
        f"当日={current_rate:.4f}, "
        f"变动={change_pct:+.2f}%, "
        f"限制=±{limit_pct:.0f}%"
    )


# ======================
# 便捷函数
# ======================
def quick_validate(
    lbma_price: float,
    usd_cny: float,
    sge_price: Optional[float] = None
) -> str:
    """
    快速校验，仅返回状态字符串
    用于简单场景或测试
    """
    from datetime import date
    result = validate_daily_data(lbma_price, usd_cny, sge_price, date.today().isoformat())
    return result["status"]


if __name__ == "__main__":
    # 测试代码
    result = validate_daily_data(
        lbma_price=2650.0,
        usd_cny=7.25,
        sge_price=620.0,
        date_str="2025-11-27"
    )
    print(f"校验结果: {result}")
