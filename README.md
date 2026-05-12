# 🌙 Moon — 场内基金折溢价套利监控

实时监控中国场内 LOF / QDII 基金的折溢价率，核心能力是通过外盘期货价格和实时汇率估算 IOPV（参考净值），修正 QDII 基金因 T-1 净值滞后造成的溢价失真。

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ 功能特性

- **实时溢价监控** — 拉取腾讯财经行情，展示场内价、净值、官方溢价率
- **IOPV 实时估算** — 利用外盘期货（黄金/原油/标普500等）+ 实时汇率，修正 T-1 净值滞后
- **套利机会识别** — 自动计算净套利空间（扣除申赎费率、佣金、滑点），标注可行动方向
- **多种展示方式** — CLI 终端表格（Rich）、Streamlit Web 仪表盘、Flask API
- **企业微信通知** — 溢价超阈值时自动推送 Webhook 告警，支持冷却机制防刷屏
- **灵活配置** — `funds.json` 集中管理基金列表、阈值、刷新频率等参数

## 📐 IOPV 估算原理

```
IOPV = T-1净值 × (外盘现价 / 外盘昨收) × (实时汇率 / T-1央行中间价)
IOPV溢价 = (场内价 / IOPV - 1) × 100%
```

| 精度等级 | 含义 |
|---------|------|
| **A** | 基于天天基金实时估值 + 外盘 + 汇率，高可信度 |
| **B** | 基于官方 T-1 净值 + 外盘 + 汇率 |
| **C** | 仅基于官方净值，无外盘修正 |
| **D** | 数据源异常，不可用 |

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/ting2tao/moon.git
cd moon
pip install -r requirements.txt
```

### CLI 使用

```bash
# 基础溢价监控
python cli.py 164701 161116 161129

# 启用 IOPV 估算（推荐）
python cli.py 164701 161116 161129 --estimate

# Watch 模式，每 30 秒刷新
python cli.py 164701 161116 161129 --estimate --watch 30

# 溢价超 5% 高亮告警
python cli.py 164701 161116 --alert 5

# 触发企业微信通知
python cli.py --notify
```

### Web 仪表盘（Streamlit）

```bash
# 默认启动
make web

# 指定端口
make web PORT=8080

# 或直接运行
streamlit run streamlit_app.py
```

仪表盘功能：侧边栏配置基金代码、阈值筛选、产品类型过滤；支持一键刷新和企业微信推送。

### Flask API

```bash
python web.py --estimate --port 5000
```

```
GET /api/funds?codes=164701,161116&estimate=true
```

### Makefile 快捷命令

```bash
make help      # 显示帮助
make install   # 安装依赖
make web       # 启动 Streamlit 仪表盘
make cli       # CLI 模式 (make cli ARGS="164701 161116")
make watch     # CLI Watch 模式
make test      # 运行测试
```

## 📁 项目结构

```
moon/
├── monitor.py        # 核心数据层：FundData 模型、腾讯行情 API 解析
├── estimates.py      # IOPV 估算引擎：外盘期货 + 汇率修正
├── arbitrage.py      # 套利计算：费率扣除、净空间、方向判断
├── providers.py      # 数据源适配层
├── cli.py            # CLI 工具：Rich 表格输出 + Watch 模式
├── streamlit_app.py  # Streamlit Web 仪表盘
├── web.py            # Flask API 服务
├── notifier.py       # 企业微信 Webhook 通知
├── funds.json        # 配置文件：基金列表、阈值、刷新参数
├── templates/        # Flask 前端模板
├── tests/            # 测试用例
├── Makefile          # 快捷命令
└── requirements.txt  # Python 依赖
```

### 数据流

```
腾讯行情API ──→ monitor.py ──→ estimates.py (IOPV) ──→ cli.py / streamlit_app.py / web.py
                    │               │
                    │         外盘期货 + 汇率API
                    │
              arbitrage.py (套利计算)
```

## ⚙️ 配置说明

编辑 `funds.json`：

```json
{
  "codes": ["164701", "161116", "161129"],
  "estimate": true,
  "default_product_types": ["LOF"],
  "alert_premium": 5,
  "estimate_alert_premium": 3,
  "net_alert_premium": 0.5,
  "gross_threshold": 1.5,
  "min_turnover_wan": 500,
  "refresh_seconds": 30
}
```

| 参数 | 说明 |
|------|------|
| `codes` | 监控的基金代码列表 |
| `estimate` | 是否默认启用 IOPV 估算 |
| `alert_premium` | 毛溢价告警阈值（%） |
| `net_alert_premium` | 净空间告警阈值（%） |
| `gross_threshold` | 筛选最低毛溢价（%） |
| `min_turnover_wan` | 最低成交额（万元） |
| `refresh_seconds` | 刷新间隔（秒） |

### 企业微信通知

设置环境变量：

```bash
export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
```

## 📊 已支持的基金类型

| 类型 | 外盘代理 | 示例基金 |
|------|---------|---------|
| 黄金 | `hf_GC` (COMEX 金) | 164701, 161116, 160719 |
| 白银 | `hf_SI` (COMEX 银) | 161226 |
| WTI 原油 | `hf_CL` | 161129, 501018 |
| Brent 原油 | `hf_OIL` | 162411 |
| 标普 500 | `hf_ES` | 161130, 160216 |

添加新基金需在 `estimates.py` 的 `FUND_CONFIGS` 中增加 `FundEstimateConfig` 条目。

## 📝 市场代码规则

| 前缀 | 交易所 |
|------|-------|
| `16xxxx`、`15xxxx` | 深交所 (`sz`) |
| `5xxxxx` | 上交所 (`sh`) |

## 📄 License

[MIT](LICENSE) © 2026 史纯涛
