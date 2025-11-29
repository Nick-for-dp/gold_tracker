# Gold Tracker - 黄金价格追踪系统

一个轻量级、自动化、本地部署的黄金价格数据采集与存储系统，用于长期追踪国际与国内黄金价格及关键汇率。

## 功能特性

- **多源数据采集**
  - LBMA 下午定盘价（通过 GoldAPI.io）
  - 上海黄金交易所 Au99.99 收盘价
  - 多币种汇率（中国货币网）
    - USD/CNY 中间价
    - JPY/CNY 中间价（100日元）
    - EUR/CNY 中间价

- **智能数据校验**
  - LBMA 价格动态校验（μ ± 3σ，支持冷启动）
  - SGE 价格区间校验（理论价 95%-112%）
  - 汇率日变动校验（±2%）

- **数据持久化**
  - SQLite 本地存储
  - 自动去重（按日期 upsert）
  - 定期备份（保留最近 N 份）

- **系统健壮性**
  - 网络请求自动重试
  - 完善的日志记录
  - 后置处理器扩展机制

## 项目结构

```
gold_tracker/
├── main.py                 # 程序入口
├── config.yaml             # 配置文件（需自行创建）
├── core/
│   └── scheduler.py        # 任务调度器
├── data_sources/
│   ├── lbma_api.py         # LBMA 价格采集
│   ├── sge_scraper.py      # SGE 价格采集
│   └── fx_fetcher.py       # 汇率采集（多币种）
├── validator/
│   └── dynamic_validator.py # 数据校验器
├── database/
│   ├── session.py          # 数据库连接（单例模式）
│   ├── repository.py       # 黄金数据访问层
│   ├── fx_repository.py    # 汇率数据访问层
│   └── db_manager.py       # 业务逻辑层
├── model/
│   ├── gold_price.py       # 黄金价格模型
│   └── exchange_rate.py    # 汇率数据模型
├── utils/
│   ├── logger.py           # 日志工具
│   └── backup_manager.py   # 备份管理
├── config/
│   └── settings.py         # 配置加载
└── data/                   # 数据库文件（自动创建）
```

## 快速开始

### 1. 环境要求

- Python >= 3.13
- [uv](https://github.com/astral-sh/uv) 包管理器（推荐）

### 2. 安装依赖

```bash
# 使用 uv
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 3. 配置

创建 `config.yaml` 文件：

```yaml
database:
  type: sqlite
  path: data/gold_tracker.db

validation:
  lbma_window_days: 20
  lbma_sigma_threshold: 3.0
  sge_theoretical_low: 0.95
  sge_theoretical_high: 1.12
  fx_daily_change_limit: 0.02

data_sources:
  goldapi:
    api_key: "your-goldapi-key"  # 从 https://www.goldapi.io 获取
    base_url: "https://www.goldapi.io/api"
  sge:
    url: "https://www.sge.com.cn/sjzx/mrhqsj"
    product_code: "Au99.99"
  fx:
    primary_url: "https://www.chinamoney.com.cn/chinese/bkccpr/"
    secondary_url: "https://www.chinamoney.com.cn/chinese/bkccpr/"

network:
  retry_times: 3
  retry_interval: 10
  timeout: 30
```

### 4. 运行

```bash
# 执行每日黄金采集（默认）
uv run python main.py

# 指定任务类型
uv run python main.py --task daily    # 黄金价格采集
uv run python main.py --task fx       # 汇率采集
uv run python main.py --task backup   # 数据库备份
uv run python main.py --task all      # 全部任务

# 静默模式
uv run python main.py -q

# 查看帮助
uv run python main.py --help
```

## 定时任务配置

### Windows 任务计划程序

| 任务 | 执行时间 | 命令 |
|------|----------|------|
| 黄金采集 | 23:30 | `python main.py --task daily` |
| 汇率采集 | 23:35 | `python main.py --task fx` |
| 每周备份 | 周日 23:45 | `python main.py --task backup` |

## 数据说明

### 黄金价格表 (daily_gold_prices)

| 字段 | 说明 |
|------|------|
| `date` | 日期 |
| `lbma_pm_usd` | LBMA 下午定盘价（美元/盎司） |
| `sge_close_cny` | SGE Au99.99 收盘价（人民币/克） |
| `usd_cny` | USD/CNY 中间价 |
| `theoretical_cny_per_gram` | 理论进口金价（人民币/克） |
| `status` | 校验状态（valid / suspicious_xxx） |

### 汇率表 (daily_exchange_rates)

| 字段 | 说明 |
|------|------|
| `date` | 日期 |
| `usd_cny` | USD/CNY 中间价 |
| `jpy_cny` | 100JPY/CNY 中间价 |
| `eur_cny` | EUR/CNY 中间价 |
| `source` | 数据来源 |
| `status` | 数据状态（valid / partial） |

### 理论进口金价计算

```
理论价 = (LBMA价格 × USD/CNY汇率) / 31.1035
```

## 扩展开发

### 添加后置处理器

```python
from core import register_processor

def my_notifier(result):
    """自定义通知处理器"""
    if result["success"]:
        # 发送通知...
        pass

# 注册处理器
register_processor(my_notifier)
```

## 依赖

- requests - HTTP 请求
- beautifulsoup4 - HTML 解析
- sqlalchemy - 数据库 ORM
- pyyaml - 配置文件解析
- python-dotenv - 环境变量

## License

MIT