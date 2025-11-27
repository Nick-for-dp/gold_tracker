import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from data_sources.lbma_api import fetch_lbma_price

@pytest.fixture
def mock_config(mocker):
    """Mock 配置"""
    config = {
        "data_sources": {
            "goldapi": {
                "api_key": "test_key",
                "base_url": "https://test.api"
            }
        },
        "network": {
            "retry_times": 1,
            "retry_interval": 0,
            "timeout": 5
        }
    }
    mocker.patch("data_sources.lbma_api.get_config", return_value=config)
    # 同时 mock base.py 中的 get_config，因为 make_request 也会用到
    mocker.patch("data_sources.base.get_config", return_value=config)
    return config

@pytest.fixture
def mock_make_request(mocker):
    """Mock 网络请求"""
    return mocker.patch("data_sources.lbma_api.make_request")

def test_fetch_lbma_price_success(mock_config, mock_make_request):
    """测试成功获取价格"""
    # 模拟 API 响应
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "timestamp": 1234567890,
        "metal": "XAU",
        "currency": "USD",
        "price": 2000.50,
        "prev_close_price": 1998.00
    }
    mock_make_request.return_value = mock_response
    
    # 执行测试：明确指定一个历史日期，避免 target_date == date.today() 逻辑
    # 假设今天不是 2020-01-01
    target_date = date(2020, 1, 1)
    result = fetch_lbma_price(target_date)
    
    # 验证结果
    assert result["success"] is True
    assert result["price"] == 2000.50
    assert result["error"] is None
    assert result["date"] == "2020-01-01"
    
    # 验证请求参数
    mock_make_request.assert_called_once()
    args, kwargs = mock_make_request.call_args
    # 历史日期应该包含日期路径
    assert args[0] == "https://test.api/XAU/USD/20200101"
    assert kwargs["headers"]["x-access-token"] == "test_key"

def test_fetch_lbma_price_no_data(mock_config, mock_make_request):
    """测试 API 返回无价格字段"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"error": "no data"}  # 无 price 字段
    mock_make_request.return_value = mock_response
    
    result = fetch_lbma_price(date(2025, 11, 27))
    
    assert result["success"] is False
    assert result["price"] is None
    assert "无 price 字段" in result["error"]

def test_fetch_lbma_price_403_auth_error(mock_config, mock_make_request):
    """测试鉴权失败"""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_make_request.return_value = mock_response
    
    result = fetch_lbma_price(date(2025, 11, 27))
    
    assert result["success"] is False
    assert result["error"] == "API Key 无效或已过期"

def test_fetch_lbma_price_404_not_found(mock_config, mock_make_request):
    """测试未找到数据（非交易日）"""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_make_request.return_value = mock_response
    
    result = fetch_lbma_price(date(2025, 11, 27))
    
    assert result["success"] is False
    assert "未找到" in result["error"]

def test_fetch_lbma_price_network_error(mock_config, mock_make_request):
    """测试网络异常"""
    # 模拟 make_request 抛出异常
    mock_make_request.side_effect = Exception("Network Error")
    
    result = fetch_lbma_price(date(2025, 11, 27))
    
    assert result["success"] is False
    assert result["price"] is None
    assert "请求异常" in result["error"]
    assert "Network Error" in result["error"]
