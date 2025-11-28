"""
SGE 黄金价格采集器
通过上海黄金交易所官网历史行情 API 获取 Au99.99 收盘价（人民币/克）
"""
from typing import Optional, Dict, Any
from datetime import date
# DEBUG: 本地测试时取消注释以下三行
# import os
# import sys
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_config
from data_sources.base import make_request


# SGE 历史行情 API（返回 OHLC 数据）
SGE_HIST_API_URL = "https://www.sge.com.cn/graph/Dailyhq"


def fetch_sge_price(target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    获取 SGE Au99.99 收盘价
    
    通过 SGE 官网历史行情 API 获取指定日期的收盘价
    API 返回按日期升序排列，取最后一条即为最新数据
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        {
            "success": True/False,
            "date": "YYYY-MM-DD",
            "price": float (人民币/克) 或 None,
            "available": True/False (当日是否有交易),
            "error": 错误信息 或 None
        }
    """
    config = get_config()
    product_code = config["data_sources"]["sge"]["product_code"]
    
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    headers = {
        "Accept": "text/html, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.sge.com.cn/sjzx/mrhq",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    try:
        response = make_request(
            SGE_HIST_API_URL, 
            method="POST", 
            headers=headers, 
            data={"instid": product_code}
        )
        
        if response.status_code != 200:
            return {
                "success": False,
                "date": date_str,
                "price": None,
                "available": False,
                "error": f"HTTP {response.status_code}"
            }
        
        time_data = response.json().get("time", [])
        if not time_data:
            return {
                "success": True,
                "date": date_str,
                "price": None,
                "available": False,
                "error": None
            }
        
        # 取最后一条记录（最新日期）
        # 格式: [date, open, close, low, high]
        latest = time_data[-1]
        latest_date = latest[0]
        
        if latest_date == date_str:
            return {
                "success": True,
                "date": date_str,
                "price": float(latest[2]),  # close
                "available": True,
                "error": None
            }
        else:
            # 目标日期无数据（非交易日或尚未更新）
            return {
                "success": True,
                "date": date_str,
                "price": None,
                "available": False,
                "error": None
            }
        
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "price": None,
            "available": False,
            "error": f"API 请求失败: {str(e)}"
        }


if __name__ == "__main__":
    # 测试代码：使用 2025-11-27 的数据核对
    test_date = date(2025, 11, 27)
    result = fetch_sge_price(test_date)
    print(f"SGE 采集结果 ({test_date}): {result}")
    
    # 也测试今天的数据
    today_result = fetch_sge_price()
    print(f"SGE 采集结果 (今天): {today_result}")
