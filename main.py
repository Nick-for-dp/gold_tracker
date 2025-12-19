"""
Gold Tracker - 贵金属价格追踪系统
主程序入口
"""
import sys
import argparse
from datetime import datetime, date

from database import init_database
from core import execute_task, TaskResult
from utils.logger import logger


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        prog="gold_tracker",
        description="贵金属价格追踪系统 - 自动采集 LBMA、SGE 黄金/白银价格和汇率数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                 # 执行每日黄金采集（默认）
  python main.py --task daily    # 执行每日黄金采集
  python main.py --task silver   # 执行每日白银采集
  python main.py --task fx       # 执行每日汇率采集
  python main.py --task backup   # 执行数据库备份
  python main.py --task all      # 执行所有任务
  
  # 补录历史数据
  python main.py --task daily --date 2023-01-01   # 补录指定日期的金价
  python main.py --task silver --date 2023-01-01  # 补录指定日期的银价
  python main.py --task fx --date 2023-01-01      # 补录指定日期的汇率

Windows 任务计划配置:
  每日黄金采集: 23:30 执行 python main.py --task daily
  每日白银采集: 23:32 执行 python main.py --task silver
  每日汇率采集: 23:35 执行 python main.py --task fx
  每周备份: 周日 23:45 执行 python main.py --task backup
        """
    )
    
    parser.add_argument(
        "--task", "-t",
        choices=["daily", "silver", "fx", "backup", "all"],
        default="daily",
        help="任务类型: daily=黄金采集, silver=白银采集, fx=汇率采集, backup=数据库备份, all=全部 (默认: daily)"
    )
    
    parser.add_argument(
        "--date", "-d",
        help="指定日期 (格式: YYYY-MM-DD)，用于补录历史数据。默认使用今天。"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="静默模式，减少输出"
    )
    
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 0.1.0"
    )
    
    return parser.parse_args()


def print_banner() -> None:
    """打印启动横幅"""
    print()
    print("╔════════════════════════════════════════╗")
    print("║    Gold Tracker - 贵金属价格追踪系统    ║")
    print("╚════════════════════════════════════════╝")
    print()


def print_result(result: TaskResult, quiet: bool = False) -> None:
    """打印任务执行结果"""
    if quiet:
        # 静默模式只输出关键信息
        status = "SUCCESS" if result.success else "FAILED"
        print(f"[{status}] {result.task_type}: {result.message}")
        return
    
    print()
    print("─" * 50)
    print("任务执行结果")
    print("─" * 50)
    print(f"  状态:   {'✅ 成功' if result.success else '❌ 失败'}")
    print(f"  类型:   {result.task_type}")
    print(f"  消息:   {result.message}")
    print(f"  开始:   {result.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束:   {result.finished_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  耗时:   {(result.finished_at - result.started_at).total_seconds():.2f} 秒")
    
    if result.details:
        print(f"  详情:   {result.details}")
    print("─" * 50)


def main() -> int:
    """
    主函数
    
    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    args = parse_args()
    
    if not args.quiet:
        print_banner()
        print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📋 任务类型: {args.task}")
        if args.date:
            print(f"📅 目标日期: {args.date}")
        print()
    
    # 解析日期参数
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ 日期格式错误: {args.date}，请使用 YYYY-MM-DD 格式")
            return 1
    
    # 1. 初始化数据库
    try:
        init_database()
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
        return 1
    
    # 2. 执行任务
    try:
        result = execute_task(args.task, target_date)
    except Exception as e:
        logger.critical(f"任务执行异常: {e}", exc_info=True)
        print(f"❌ 任务执行异常: {e}")
        return 1
    
    # 3. 输出结果
    print_result(result, args.quiet)
    
    # 4. 返回退出码
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
