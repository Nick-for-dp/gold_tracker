"""
汇率采集器
爬取中国外汇交易中心获取 USD/CNY 中间价
"""
import time
import re
from typing import Optional, Dict, Any
from datetime import date
import requests
from bs4 import BeautifulSoup

from config import get_config
from data_sources.base import make_request


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
    config = get_config()
    fx_config = config["data_sources"]["fx"]
    
    primary_url = fx_config["primary_url"]
    
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    
    # 首先尝试中国货币网 API（更稳定）
    # 注意：内部函数现在自己处理超时，不再需要传递 timeout
    result = _fetch_from_chinamoney_api(date_str)
    if result["success"]:
        return result
    
    # 备用：爬取页面
    last_error = result.get("error", "API 获取失败")
    
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    try:
        response = make_request(primary_url, headers=headers)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            result = _parse_chinamoney_page(response.text, date_str)
            if result["success"]:
                return result
            else:
                last_error = result.get("error", "解析失败")
        else:
            last_error = f"HTTP {response.status_code}"
            
    except Exception as e:
        last_error = f"请求异常: {str(e)}"
    
    # 主源失败，尝试备用源
    fallback_result = _fetch_from_fallback(date_str)
    if fallback_result["success"]:
        return fallback_result
    
    return {
        "success": False,
        "date": date_str,
        "rate": None,
        "error": f"所有数据源均失败: {last_error}"
    }


def _fetch_from_chinamoney_api(date_str: str) -> Dict[str, Any]:
    """
    通过中国货币网 API 获取汇率
    API 地址: https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcsrHis498.do
    """
    api_url = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew.do"
    
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.chinamoney.com.cn/chinese/bkccpr/",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    # 请求参数
    params = {
        "startDate": date_str,
        "endDate": date_str,
        "currency": "USD/CNY",
        "pageNum": 1,
        "pageSize": 1
    }
    
    try:
        response = make_request(api_url, params=params, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # API 返回格式：
            # {
            #   "code": 0,
            #   "data": {
            #     "records": [{"values": ["2024-01-15", "7.1088", ...]}]
            #   }
            # }
            records = data.get("data", {}).get("records", [])
            if records and len(records) > 0:
                values = records[0].get("values", [])
                if len(values) >= 2:
                    rate = float(values[1])
                    return {
                        "success": True,
                        "date": date_str,
                        "rate": rate,
                        "error": None
                    }
        
        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "error": "API 返回数据格式异常"
        }
    
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "error": f"API 请求失败: {str(e)}"
        }


def _parse_chinamoney_page(html: str, date_str: str) -> Dict[str, Any]:
    """
    解析中国货币网页面，提取 USD/CNY 中间价
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 查找包含 USD/CNY 的表格行
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                row_text = row.get_text()
                if 'USD' in row_text and 'CNY' in row_text:
                    cells = row.find_all(['td', 'th'])
                    for cell in cells:
                        cell_text = cell.get_text().strip()
                        # 汇率格式：7.xxxx
                        if re.match(r'^[67]\.\d{4}$', cell_text):
                            return {
                                "success": True,
                                "date": date_str,
                                "rate": float(cell_text),
                                "error": None
                            }
        
        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "error": "未找到 USD/CNY 汇率数据"
        }
    
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "error": f"页面解析错误: {str(e)}"
        }


def _fetch_from_fallback(date_str: str) -> Dict[str, Any]:
    """
    备用方案：通过免费汇率 API 获取
    使用 exchangerate-api.com 或类似服务
    """
    # 备用 API（无需 key 的免费服务）
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    
    try:
        response = make_request(url)
        
        if response.status_code == 200:
            data = response.json()
            rates = data.get("rates", {})
            cny_rate = rates.get("CNY")
            
            if cny_rate:
                return {
                    "success": True,
                    "date": date_str,
                    "rate": float(cny_rate),
                    "error": None
                }
        
        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "error": "备用 API 无数据"
        }
    
    except Exception as e:
        return {
            "success": False,
            "date": date_str,
            "rate": None,
            "error": f"备用 API 请求失败: {str(e)}"
        }


if __name__ == "__main__":
    # 测试代码
    result = fetch_usd_cny_rate()
    print(f"汇率采集结果: {result}")
