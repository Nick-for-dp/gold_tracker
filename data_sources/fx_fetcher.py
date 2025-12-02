"""
汇率采集器
爬取中国外汇交易中心获取 USD/CNY 中间价
"""
from typing import Optional, Dict, Any, List
from datetime import date, timedelta
# DEBUG: 本地测试时取消注释以下三行
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_sources.base import make_request


def _fetch_from_chinamoney_api(date_str: str, currency: str = "USD/CNY") -> Dict[str, Any]:
    """
    通过中国货币网 API 获取汇率
    
    Args:
        date_str: 日期字符串 YYYY-MM-DD
        currency: 货币对，如 "USD/CNY", "JPY/CNY", "EUR/CNY"
    
    Returns:
        {
            "success": True/False,
            "date": "YYYY-MM-DD",
            "rate": float 或 None,
            "currency": 货币对,
            "error": 错误信息 或 None
        }
    """
    api_url = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew.do"
    
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.chinamoney.com.cn",
        "Referer": "https://www.chinamoney.com.cn/chinese/bkccpr/",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    
    # 请求参数 (POST form data)
    form_data = {
        "startDate": date_str,
        "endDate": date_str,
        "currency": currency,
        "pageNum": 1,
        "pageSize": 1
    }
    
    try:
        response = make_request(api_url, method="POST", data=form_data, headers=headers)
        
        if response is None:
            return {
                "success": False,
                "date": date_str,
                "rate": None,
                "currency": currency,
                "error": "请求返回空响应"
            }
        
        if response.status_code != 200:
            return {
                "success": False,
                "date": date_str,
                "rate": None,
                "currency": currency,
                "error": f"HTTP {response.status_code}"
            }
        
        data = response.json()
        if data is None:
            return {
                "success": False,
                "date": date_str,
                "rate": None,
                "currency": currency,
                "error": "API 返回空数据"
            }
        
        # API 返回格式：
        # {
        #   "code": 0,
        #   "data": {
        #     "head": ["USD/CNY", "EUR/CNY", ...],
        #     "searchlist": ["USD/CNY", "EUR/CNY", ...],
        #   },
        #    "records": [{"date": "2025-12-01", "values": ["7.1088", ...]}]
        # }

        records = data.get("records", [])
        if not records:
            return {
                "success": False,
                "date": date_str,
                "rate": None,
                "currency": currency,
                "error": "API 返回记录为空"
            }

        # 获取数据日期
        today_fx_obj = records[0]
        fx_date = today_fx_obj.get("date", "")
        
        if fx_date != date_str:
            return {
                "success": False,
                "date": date_str,
                "rate": None,
                "currency": currency,
                "error": f"日期不匹配 (API返回: {fx_date})"
            }

        # 构建汇率映射字典 {币种: 汇率}
        data_obj = data.get("data", {})
        currency_list = data_obj.get("searchlist", [])
        fx_values = today_fx_obj.get("values", [])
        rate_map = dict(zip(currency_list, fx_values))
        
        if currency in rate_map:
            return {
                "success": True,
                "date": date_str,
                "rate": round(float(rate_map[currency]), 3),
                "currency": currency,
                "error": None
            }

        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "currency": currency,
            "error": f"API 无 {currency} 数据（可能为非交易日）"
        }
    
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "currency": currency,
            "error": f"API 请求失败: {str(e)}"
        }


def fetch_usd_cny_rate(target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    获取 USD/CNY 中间价
    
    Args:
        target_date: 目标日期，默认为当天
    
    Returns:
        {
            "success": True/False,
            "date": "YYYY-MM-DD",
            "rate": float 或 None,
            "error": 错误信息 或 None
        }
    """
    # 默认使用当天日期
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    # 1. 尝试使用通用接口获取
    result = fetch_multi_currency_rates(target_date, currencies=["USD/CNY"])
    
    if result["success"] and "usd_cny" in result["rates"]:
        return {
            "success": True,
            "date": result["date"],
            "rate": result["rates"]["usd_cny"],
            "error": None
        }
    
    # 2. 获取失败，提取错误信息
    last_error = "未获取到数据"
    if result["errors"]:
        last_error = "; ".join(result["errors"])
    
    return {
        "success": False,
        "date": date_str,
        "rate": None,
        "error": f"获取失败: {last_error}"
    }


def fetch_multi_currency_rates(
    target_date: Optional[date] = None,
    currencies: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    批量获取多个货币对的汇率
    
    Args:
        target_date: 目标日期，默认为当天
        currencies: 货币对列表，默认 ["USD/CNY", "JPY/CNY", "EUR/CNY"]
    
    Returns:
        {
            "success": True/False,
            "date": "YYYY-MM-DD",
            "rates": {
                "usd_cny": 7.1234,
                "jpy_cny": 4.7890,  # 100日元对人民币
                "eur_cny": 7.6543
            },
            "source": "chinamoney",
            "errors": []  # 失败的货币对信息
        }
    """
    # 默认货币对列表
    if currencies is None:
        currencies = ["USD/CNY", "100JPY/CNY", "EUR/CNY"]
    # 默认使用当天日期
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    rates = {}
    errors = []
    
    for pair in currencies:
        result = _fetch_from_chinamoney_api(date_str, currency=pair)
        if pair == "100JPY/CNY":
            key = "jpy_cny"
        else:
            key = pair.lower().replace("/", "_")  # "USD/CNY" -> "usd_cny"
        
        if result["success"]:
            rates[key] = result["rate"]
        else:
            errors.append(f"{pair}: {result['error']}")
    
    return {
        "success": len(rates) > 0,
        "date": date_str,
        "rates": rates,
        "source": "chinamoney",
        "errors": errors
    }


if __name__ == "__main__":
    # 测试代码
    print("=== 测试单币种获取 ===")
    result = fetch_usd_cny_rate()
    print(f"USD/CNY 汇率: {result}")
    
    # print("\n=== 测试多币种获取 ===")
    multi_result = fetch_multi_currency_rates()
    print(f"多币种汇率: {multi_result}")
