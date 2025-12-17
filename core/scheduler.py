"""
任务调度器
封装调度逻辑，支持后置处理器扩展
"""
from typing import Callable, List, Optional
from datetime import datetime, date
from dataclasses import dataclass, field

from database import run_daily_task, run_daily_fx_task, run_daily_silver_task, CollectionResult, FxCollectionResult, SilverCollectionResult
from utils.logger import logger
from utils.backup_manager import backup_database


# ======================
# 类型定义
# ======================
# 后置处理器函数签名: (result: CollectionResult) -> None
PostProcessor = Callable[[CollectionResult], None]


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    task_type: str
    message: str
    started_at: datetime
    finished_at: datetime
    details: Optional[dict] = None


# ======================
# 后置处理器注册表
# ======================
_post_processors: List[PostProcessor] = []


def register_processor(processor: PostProcessor) -> None:
    """注册后置处理器"""
    if processor not in _post_processors:
        _post_processors.append(processor)


def unregister_processor(processor: PostProcessor) -> None:
    """注销后置处理器"""
    if processor in _post_processors:
        _post_processors.remove(processor)


def clear_processors() -> None:
    """清空所有后置处理器"""
    _post_processors.clear()


# ======================
# 内置后置处理器
# ======================
def log_result_processor(result: CollectionResult) -> None:
    """
    日志记录处理器
    记录采集结果到日志系统
    """
    if result["success"]:
        logger.info(f"采集成功: {result['date']}")
        logger.info(f"状态: {result['validation_status']}")
        logger.info(f"来源: LBMA={result['lbma_source']}, SGE={result['sge_source']}, FX={result['fx_source']}")
    else:
        logger.error(f"采集失败: {result['date']}")
        logger.error(f"错误: {result['error']}")


def summary_printer_processor(result: CollectionResult) -> None:
    """
    数据摘要打印处理器
    打印采集到的数据摘要
    """
    if not result["success"] or result["record"] is None:
        return
    
    record = result["record"]
    print(f"\n📊 {record['date']} 黄金价格数据")
    print("=" * 40)
    print(f"  LBMA 定盘价:    ${record['lbma_pm_usd']:.2f}/盎司")
    print(f"  USD/CNY 汇率:   {record['usd_cny']:.4f}")
    print(f"  理论进口金价:   ¥{record['theoretical_cny_per_gram']:.2f}/克")
    
    if record["sge_close_cny"] is not None:
        print(f"  SGE Au99.99:    ¥{record['sge_close_cny']:.2f}/克")
        # 计算溢价率
        if record["theoretical_cny_per_gram"] > 0:
            premium = (record["sge_close_cny"] / record["theoretical_cny_per_gram"] - 1) * 100
            print(f"  SGE 溢价率:     {premium:+.2f}%")
    else:
        print(f"  SGE Au99.99:    无交易")
    
    print(f"  数据状态:       {record['status']}")
    print("=" * 40)


# ======================
# 后置处理器执行
# ======================
def _run_post_processors(result: CollectionResult) -> None:
    """
    执行所有已注册的后置处理器
    单个处理器失败不影响其他处理器
    """
    for processor in _post_processors:
        try:
            processor(result)
        except Exception as e:
            # 处理器失败只打印警告，不中断流程
            logger.warning(f"后置处理器 {processor.__name__} 执行失败: {e}")


# ======================
# 任务执行函数
# ======================
def run_daily_collection(target_date: Optional[date] = None) -> TaskResult:
    """
    执行每日数据采集任务
    
    流程:
    1. 记录开始时间
    2. 调用 db_manager.run_daily_task()
    3. 执行后置处理器
    4. 返回任务结果
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        TaskResult: 任务执行结果
    """
    started_at = datetime.now()
    
    try:
        # 执行采集
        result = run_daily_task(target_date)
        
        # 执行后置处理器
        _run_post_processors(result)
        
        finished_at = datetime.now()
        
        if result["success"]:
            return TaskResult(
                success=True,
                task_type="daily_collection",
                message=f"采集成功: {result['date']}, 状态: {result['validation_status']}",
                started_at=started_at,
                finished_at=finished_at,
                details={
                    "date": result["date"],
                    "validation_status": result["validation_status"],
                    "lbma_source": result["lbma_source"],
                    "sge_source": result["sge_source"],
                    "fx_source": result["fx_source"],
                }
            )
        else:
            return TaskResult(
                success=False,
                task_type="daily_collection",
                message=f"采集失败: {result['error']}",
                started_at=started_at,
                finished_at=finished_at,
                details={"error": result["error"]}
            )
    
    except Exception as e:
        finished_at = datetime.now()
        return TaskResult(
            success=False,
            task_type="daily_collection",
            message=f"任务异常: {str(e)}",
            started_at=started_at,
            finished_at=finished_at,
            details={"exception": str(e)}
        )


def run_fx_collection(target_date: Optional[date] = None) -> TaskResult:
    """
    执行每日汇率采集任务
    
    采集 USD/CNY、JPY/CNY、EUR/CNY 汇率并存入数据库。
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        TaskResult: 任务执行结果
    """
    started_at = datetime.now()
    
    try:
        result = run_daily_fx_task(target_date)
        finished_at = datetime.now()
        
        if result["success"]:
            msg = f"汇率采集成功: {result['date']}, 货币: {result['currencies_collected']}"
            logger.info(msg)
            return TaskResult(
                success=True,
                task_type="fx_collection",
                message=msg,
                started_at=started_at,
                finished_at=finished_at,
                details={
                    "date": result["date"],
                    "source": result["source"],
                    "currencies_collected": result["currencies_collected"],
                }
            )
        else:
            msg = f"汇率采集失败: {result['error']}"
            logger.error(msg)
            return TaskResult(
                success=False,
                task_type="fx_collection",
                message=msg,
                started_at=started_at,
                finished_at=finished_at,
                details={"error": result["error"]}
            )
    
    except Exception as e:
        finished_at = datetime.now()
        return TaskResult(
            success=False,
            task_type="fx_collection",
            message=f"汇率采集异常: {str(e)}",
            started_at=started_at,
            finished_at=finished_at,
            details={"exception": str(e)}
        )


def run_silver_collection(target_date: Optional[date] = None) -> TaskResult:
    """
    执行每日白银数据采集任务
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        TaskResult: 任务执行结果
    """
    started_at = datetime.now()
    
    try:
        result = run_daily_silver_task(target_date)
        finished_at = datetime.now()
        
        if result["success"]:
            msg = f"白银采集成功: {result['date']}, 状态: {result['validation_status']}"
            logger.info(msg)
            
            # 打印白银数据摘要
            if result["record"]:
                record = result["record"]
                print(f"\n🥈 {record['date']} 白银价格数据")
                print("=" * 40)
                print(f"  LBMA 定盘价:    ${record['lbma_pm_usd']:.2f}/盎司")
                print(f"  USD/CNY 汇率:   {record['usd_cny']:.4f}")
                print(f"  理论进口银价:   ¥{record['theoretical_cny_per_gram']:.4f}/克")
                if record["sge_close_cny"] is not None:
                    print(f"  SGE Ag99.99:    ¥{record['sge_close_cny']:.4f}/克")
                    if record["theoretical_cny_per_gram"] > 0:
                        premium = (record["sge_close_cny"] / record["theoretical_cny_per_gram"] - 1) * 100
                        print(f"  SGE 溢价率:     {premium:+.2f}%")
                else:
                    print(f"  SGE Ag99.99:    无交易")
                print(f"  数据状态:       {record['status']}")
                print("=" * 40)
            
            return TaskResult(
                success=True,
                task_type="silver_collection",
                message=msg,
                started_at=started_at,
                finished_at=finished_at,
                details={
                    "date": result["date"],
                    "validation_status": result["validation_status"],
                    "lbma_source": result["lbma_source"],
                    "sge_source": result["sge_source"],
                    "fx_source": result["fx_source"],
                }
            )
        else:
            msg = f"白银采集失败: {result['error']}"
            logger.error(msg)
            return TaskResult(
                success=False,
                task_type="silver_collection",
                message=msg,
                started_at=started_at,
                finished_at=finished_at,
                details={"error": result["error"]}
            )
    
    except Exception as e:
        finished_at = datetime.now()
        return TaskResult(
            success=False,
            task_type="silver_collection",
            message=f"白银采集异常: {str(e)}",
            started_at=started_at,
            finished_at=finished_at,
            details={"exception": str(e)}
        )


def run_weekly_backup() -> TaskResult:
    """
    执行每周数据库备份任务
    
    Returns:
        TaskResult: 任务执行结果
    """
    started_at = datetime.now()
    
    try:
        logger.info("开始执行数据库备份...")
        backup_path = backup_database()
        
        finished_at = datetime.now()
        
        if backup_path:
            return TaskResult(
                success=True,
                task_type="weekly_backup",
                message=f"备份成功: {backup_path}",
                started_at=started_at,
                finished_at=finished_at,
                details={"backup_path": backup_path}
            )
        else:
            return TaskResult(
                success=False,
                task_type="weekly_backup",
                message="备份失败，请检查日志",
                started_at=started_at,
                finished_at=finished_at,
            )
    
    except Exception as e:
        finished_at = datetime.now()
        logger.error(f"备份异常: {e}", exc_info=True)
        return TaskResult(
            success=False,
            task_type="weekly_backup",
            message=f"备份异常: {str(e)}",
            started_at=started_at,
            finished_at=finished_at,
            details={"exception": str(e)}
        )


def execute_task(task_type: str, target_date: Optional[date] = None) -> TaskResult:
    """
    统一任务执行入口
    
    Args:
        task_type: 任务类型
            - "daily": 每日黄金采集
            - "silver": 每日白银采集
            - "fx": 每日汇率采集
            - "backup": 数据库备份
            - "all": 执行所有任务
        target_date: 目标日期 (仅对 daily、silver 和 fx 任务有效)
    
    Returns:
        TaskResult: 任务执行结果（all 时返回综合结果）
    """
    if task_type == "daily":
        return run_daily_collection(target_date)
    
    elif task_type == "silver":
        return run_silver_collection(target_date)
    
    elif task_type == "fx":
        return run_fx_collection(target_date)
    
    elif task_type == "backup":
        return run_weekly_backup()
    
    elif task_type == "all":
        # 依次执行所有任务
        daily_result = run_daily_collection(target_date)
        silver_result = run_silver_collection(target_date)
        fx_result = run_fx_collection(target_date)
        backup_result = run_weekly_backup()
        
        # 返回综合结果
        all_success = daily_result.success and silver_result.success and fx_result.success and backup_result.success
        return TaskResult(
            success=all_success,
            task_type="all",
            message=f"daily: {daily_result.success}, silver: {silver_result.success}, fx: {fx_result.success}, backup: {backup_result.success}",
            started_at=daily_result.started_at,
            finished_at=backup_result.finished_at,
            details={
                "daily": daily_result.message,
                "silver": silver_result.message,
                "fx": fx_result.message,
                "backup": backup_result.message,
            }
        )
    
    else:
        return TaskResult(
            success=False,
            task_type=task_type,
            message=f"未知任务类型: {task_type}",
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )


# ======================
# 初始化：注册默认处理器
# ======================
def init_default_processors() -> None:
    """注册默认的后置处理器"""
    register_processor(log_result_processor)
    register_processor(summary_printer_processor)


# 模块加载时自动注册默认处理器
init_default_processors()


if __name__ == "__main__":
    # 测试：执行每日采集
    print("=" * 50)
    print("测试：执行每日采集任务")
    print("=" * 50)
    
    result = run_daily_collection()
    
    print(f"\n任务结果:")
    print(f"  成功: {result.success}")
    print(f"  类型: {result.task_type}")
    print(f"  消息: {result.message}")
    print(f"  耗时: {(result.finished_at - result.started_at).total_seconds():.2f}秒")
