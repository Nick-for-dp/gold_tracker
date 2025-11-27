import time
from typing import Optional, Dict, Any
import requests
from requests.exceptions import RequestException

from config import get_config
from utils.logger import logger


def make_request(
    url: str, 
    method: str = "GET",
    headers: Optional[Dict] = None,
    params: Optional[Dict] = None,
    data: Optional[Dict] = None,
    timeout: Optional[int] = None
) -> requests.Response:
    """
    发送 HTTP 请求，自动处理重试逻辑
    
    Args:
        url: 请求 URL
        method: 请求方法 (GET/POST)
        headers: 请求头
        params: URL 参数 (GET)
        data: Body 数据 (POST)
        timeout: 超时时间 (秒)，如果不指定则使用配置中的默认值
        
    Returns:
        requests.Response: 响应对象
        
    Raises:
        requests.RequestException: 如果所有重试都失败
    """
    config = get_config()
    network_config = config.get("network", {})
    
    retry_times = network_config.get("retry_times", 3)
    retry_interval = network_config.get("retry_interval", 10)
    default_timeout = network_config.get("timeout", 30)
    
    current_timeout = timeout if timeout is not None else default_timeout
    
    last_exception = None
    
    # 默认 User-Agent
    default_headers = {
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if headers:
        default_headers.update(headers)
        
    for attempt in range(1, retry_times + 1):
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=default_headers, params=params, timeout=current_timeout)
            elif method.upper() == "POST":
                # 根据 data 类型决定传 data 还是 json
                # 这里假设如果是 dict 且没有明确 Content-Type，优先根据习惯
                # 但为了通用性，直接透传给 data 参数，调用者自己决定是 data 还是 json
                # 修正：通常 requests 的 data 参数接受 dict 会转 form-urlencoded，json 参数会转 json body
                # 这里我们简化一下，只支持 data (form-urlencoded)
                response = requests.post(url, headers=default_headers, data=data, timeout=current_timeout)
            else:
                raise ValueError(f"不支持的方法: {method}")
            
            return response
            
        except RequestException as e:
            last_exception = e
            logger.warning(f"请求失败 ({attempt}/{retry_times}): {url} - {str(e)}")
            
            if attempt < retry_times:
                time.sleep(retry_interval)
        except Exception as e:
            # 捕获其他可能的异常
            last_exception = e
            logger.error(f"未预期的请求错误 ({attempt}/{retry_times}): {url} - {str(e)}")
            if attempt < retry_times:
                time.sleep(retry_interval)
    
    # 所有重试都失败
    if last_exception:
        raise last_exception
    else:
        raise RequestException(f"请求失败，重试 {retry_times} 次")
