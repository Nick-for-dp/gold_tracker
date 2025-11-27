"""
SGE 黄金价格采集器
通过上海黄金交易所官网 API 获取 Au99.99 收盘价（人民币/克）
"""
import time
import re
from typing import Optional, Dict, Any
from datetime import date
import requests

from config import get_config
from data_sources.base import make_request


# SGE 官网行情 API
SGE_API_URL = "https://www.sge.com.cn/graph/quotations"


def fetch_sge_price(target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    获取 SGE Au99.99 收盘价
    
    通过 SGE 官网 API 获取实时/当日行情数据
    
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
    sge_config = config["data_sources"]["sge"]
    
    product_code = sge_config["product_code"]
    
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.sge.com.cn/",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    # POST 请求参数
    data = {
        "instid": product_code  # Au99.99
    }
    
    try:
        response = make_request(SGE_API_URL, method="POST", headers=headers, data=data)
        
        if response.status_code == 200:
            result = _parse_sge_api_response(response.json(), date_str)
            if result["success"] or result.get("available") is False:
                return result
            else:
                return {
                    "success": False,
                    "date": date_str,
                    "price": None,
                    "available": False,
                    "error": result.get("error", "解析失败")
                }
        else:
            return {
                "success": False,
                "date": date_str,
                "price": None,
                "available": False,
                "error": f"HTTP {response.status_code}"
            }
            
    except Exception as e:
        # 所有重试失败后，返回不可用状态（不阻塞主流程）
        return {
            "success": False,
            "date": date_str,
            "price": None,
            "available": False,
            "error": f"API 请求失败: {str(e)}"
        }


def _parse_sge_api_response(data: dict, date_str: str) -> Dict[str, Any]:
    """
    解析 SGE API 返回的 JSON 数据
    
    API 返回格式：
    {
        "times": ["20:00", "20:01", ...],
        "prices": ["944.45", "944.45", ...],
        "max": 945,
        "heyue": "Au99.99",
        "delaystr": "2025年11月27日 11:37:52"
    }
    """
    try:
        prices = data.get("prices", [])
        heyue = data.get("heyue", "")
        
        if not prices:
            # 无价格数据，可能是非交易日
            return {
                "success": True,
                "date": date_str,
                "price": None,
                "available": False,
                "error": None
            }
        
        # 获取最后一个有效价格（收盘价）
        # 从后往前找第一个有效的价格
        close_price = None
        for price_str in reversed(prices):
            if price_str and price_str.strip():
                try:
                    price = float(price_str)
                    # SGE Au99.99 价格通常在 300-1500 元/克范围
                    if 300 <= price <= 1500:
                        close_price = price
                        break
                except ValueError:
                    continue
        
        if close_price is not None:
            return {
                "success": True,
                "date": date_str,
                "price": close_price,
                "available": True,
                "error": None
            }
        
        return {
            "success": False,
            "date": date_str,
            "price": None,
            "available": False,
            "error": f"未找到有效的 {heyue} 价格数据"
        }
    
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "price": None,
            "available": False,
            "error": f"API 响应解析错误: {str(e)}"
        }


def fetch_sge_price_alternative(target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    备用方案：通过新浪财经获取 SGE 价格
    URL: https://finance.sina.com.cn/futures/quotes/AU0.shtml
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    url = "https://hq.sinajs.cn/list=hf_AU"
    
    headers = {
        "Referer": "https://finance.sina.com.cn/"
    }
    
    try:
        response = make_request(url, headers=headers)
        response.encoding = 'gbk'
        
        if response.status_code == 200:
            # 新浪返回格式: var hq_str_hf_AU="...,收盘价,...";
            text = response.text
            match = re.search(r'"([^"]+)"', text)
            if match:
                data = match.group(1).split(',')
                if len(data) >= 4:
                    price = float(data[3])  # 收盘价位置可能需要调整
                    return {
                        "success": True,
                        "date": date_str,
                        "price": price,
                        "available": True,
                        "error": None
                    }
        
        return {
            "success": False,
            "date": date_str,
            "price": None,
            "available": False,
            "error": "备用源解析失败"
        }
    
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "price": None,
            "available": False,
            "error": f"备用源请求失败: {str(e)}"
        }


if __name__ == "__main__":
    # 测试代码
    result = fetch_sge_price()
    print(f"SGE 采集结果: {result}")
