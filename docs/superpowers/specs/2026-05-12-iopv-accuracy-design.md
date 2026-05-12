# IOPV 精度优化设计

## 目标

提升 LOF/QDII 基金 IOPV 估算精度，使溢价率可用于溢价申购套利决策。

## 当前问题

### 问题 1：估算净值直接当 IOPV，漏算当日外盘变动

`estimates.py:329-343`：当天天基金估算净值可用时，代码直接用作 IOPV，设 `foreign_factor=1.0, fx_factor=1.0`。

天天基金的估算净值基于 T-1 外盘收盘价 + 当天 A 股持仓估值，并不包含当天外盘实时变动。正确做法：

```
IOPV = 估算净值 × (外盘现价 / 外盘昨收) × (实时汇率 / T-1 汇率)
```

### 问题 2：外盘昨收参考点不准

腾讯 `hf_GC` 等期货的"昨收"在不同时段含义不同（夜盘 vs 日盘），导致 foreign_factor 偏差。

### 问题 3：akshare 央行中间价不稳定

`akshare.currency_boc_sina()` 经常失败，fallback 到实时汇率后 `fx_factor ≈ 1.0`，丢失汇率修正。

### 问题 4：缺少精度感知

无法判断当前 IOPV 是否可靠。

## 设计方案：多源融合 + 精度分级

### 1. 修复 IOPV 公式（核心改动）

**修改文件**：`estimates.py` — `estimate_iopv()` 和 `estimate_all()`

当 `base_source == "estimated_nav"` 时，不再跳过 foreign_factor 和 fx_factor 计算。公式统一为：

```python
iopv = base_nav × foreign_factor × fx_factor
```

无论 base_nav 来自天天基金估算还是官方净值，都应用外盘和汇率修正。

### 2. 改善外盘参考点

**修改文件**：`estimates.py` — `_parse_tencent_foreign()` 和 `fetch_foreign_quotes()`

- 期货（`hf_*`）：使用 `fields[0]`（现价）和 `fields[7]`（昨结算/昨收）
- 股票/ETF（`us*`, `hk*`）：使用 `fields[3]`（现价）和 `fields[4]`（昨收）

当前逻辑已区分这两种格式，保持不变。新增：记录数据时间戳，标注数据新鲜度。

### 3. 多源汇率融合

**修改文件**：`estimates.py` — `fetch_fx_rate()`

汇率获取优先级链：

```
1. open.er-api.com 实时汇率 → realtime_cnh
2. akshare 央行中间价 → base_cnh
3. 新增备用：新浪财经汇率接口 → base_cnh fallback
4. 最终 fallback：用 realtime_cnh 作为 base（fx_factor ≈ 1.0，标注精度降级）
```

新增备用源：
- `https://hq.sinajs.cn/rn=xxx&list=fx_susdcnh` — 新浪实时 USD/CNH
- 手动硬编码近期央行中间价作为极端 fallback（仅在所有 API 失败时使用，标注精度为 C）

### 4. 精度分级系统

**修改文件**：`estimates.py` — `EstimateResult` 新增 `precision` 字段

精度等级定义：

| 等级 | 条件 | 含义 |
|------|------|------|
| A | 估算净值 + 外盘实时 + 汇率实时 | 最可信，可用于套利决策 |
| B | 估算净值 + 外盘实时 + 汇率近似 | 可参考，汇率有小误差 |
| C | 官方净值（可能 T-2）+ 外盘实时 | 净值滞后，溢价可能虚高/虚低 |
| D | 数据缺失或计算失败 | 不可信 |

精度等级影响 UI 展示和告警逻辑：
- A 级：绿色标记，正常告警
- B 级：黄色标记，正常告警
- C 级：橙色标记，告警附带警告
- D 级：红色标记，不告警

### 5. 数据新鲜度标注

**修改文件**：`monitor.py` — `FundData` 新增字段

```python
iopv_precision: str = "D"          # A/B/C/D
foreign_data_age_min: int = 0      # 外盘数据延迟（分钟）
fx_data_age_min: int = 0           # 汇率数据延迟（分钟）
```

### 6. UI 展示优化

**修改文件**：`streamlit_app.py`, `cli.py`

- IOPV 列旁显示精度等级标记（A/B/C/D）
- C/D 级数据用不同颜色高亮
- 新增"数据源详情"列，显示 base_nav 来源、外盘代理、汇率来源

## 改动文件清单

| 文件 | 改动 |
|------|------|
| `estimates.py` | 修复 IOPV 公式、多源汇率、精度分级、数据新鲜度 |
| `monitor.py` | FundData 新增精度字段、enrich_with_iopv 传递精度信息 |
| `arbitrage.py` | 无需改动 |
| `cli.py` | 精度等级列、颜色编码 |
| `streamlit_app.py` | 精度等级列、数据源详情 |
| `providers.py` | 无需改动 |

## 不做的事

- 不自建 NAV 推算引擎（持仓数据难获取）
- 不引入新的外部依赖（仅用现有 requests + akshare）
- 不改变告警阈值逻辑（精度分级只影响展示和置信度）
