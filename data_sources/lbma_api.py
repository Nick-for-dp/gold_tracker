"""
LBMA 黄金价格采集器
通过 GoldAPI.io 获取 LBMA 下午定盘价（美元/盎司）
"""
from typing import Optional, Dict, Any
from datetime import date

from config import get_config
from data_sources.base import make_request


def fetch_lbma_price(target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    获取 LBMA 下午定盘价
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        {
            "success": True/False,
            "date": "YYYY-MM-DD",
            "price": float (美元/盎司) 或 None,
            "error": 错误信息 或 None
        }
    """
    config = get_config()
    api_config = config["data_sources"]["goldapi"]
    api_key = api_config["api_key"]
    base_url = api_config["base_url"]
    
    # 目标日期
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    # API 请求 URL
    # GoldAPI 格式: /XAU/USD/YYYYMMDD 获取历史数据，或 /XAU/USD 获取最新数据
    if target_date == date.today():
        url = f"{base_url}/XAU/USD"
    else:
        url = f"{base_url}/XAU/USD/{target_date.strftime('%Y%m%d')}"
    
    headers = {
        "x-access-token": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        response = make_request(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # GoldAPI 返回格式：
            # {
            #   "timestamp": 1234567890,
            #   "metal": "XAU",
            #   "currency": "USD",
            #   "price": 1950.50,
            #   "prev_close_price": 1948.00,
            #   ...
            # }
            price = data.get("price")
            if price is not None:
                return {
                    "success": True,
                    "date": date_str,
                    "price": float(price),
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "date": date_str,
                    "price": None,
                    "error": "API 返回数据中无 price 字段"
                }
        
        elif response.status_code == 401:
            return {
                "success": False,
                "date": date_str,
                "price": None,
                "error": "API Key 无效或已过期"
            }
        
        elif response.status_code == 404:
            return {
                "success": False,
                "date": date_str,
                "price": None,
                "error": f"未找到 {date_str} 的 LBMA 数据（可能为非交易日）"
            }
        
        elif response.status_code == 429:
            return {
                "success": False,
                "date": date_str,
                "price": None,
                "error": "API 请求次数超限"
            }
        
        else:
            return {
                "success": False,
                "date": date_str,
                "price": None,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
    
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "price": None,
            "error": f"请求异常: {str(e)}"
        }


if __name__ == "__main__":
    # 测试代码
    result = fetch_lbma_price()
    print(f"LBMA 采集结果: {result}")
