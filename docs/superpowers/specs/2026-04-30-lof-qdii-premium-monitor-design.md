# LOF-First On-Exchange Arbitrage Monitor Design

## Context

This project is a lightweight monitor for on-exchange fund discount and premium opportunities, with LOF as the primary target and ETF support as a compatible extension. It focuses on manual arbitrage monitoring, not automatic trading. The tool fetches listed prices, official NAV or real-time reference NAV (IOPV), liquidity, creation/subscription and redemption status when available, and estimated fee-adjusted spread, then ranks opportunities and sends alerts.

Example target funds:

- `164701`: 汇添富黄金LOF
- `161116`: 易方达黄金主题LOF
- `161129`: 易方达原油LOF

The working directory already contains an initial `monitor.py` implementation with Tencent quote parsing and an Eastmoney historical NAV helper. This design treats that file as the starting point and refines it into a more reliable small tool.

The scope is LOF-first. ETFs can be monitored with the same table, alerts, IOPV, liquidity, and fee-adjusted spread framework, but LOF fields and workflows remain the MVP priority. Closed-end funds and automatic order execution are out of scope for the MVP.

## Goals

- Fetch current listed fund price, latest available NAV or IOPV, NAV date, change percentage, volume, and premium rate.
- Calculate real-time reference NAV (IOPV) for configured QDII, commodity-linked LOFs, and ETF products using foreign-market proxy prices and FX.
- Compare multiple LOF and selected ETF products in one view, defaulting to LOF-first sorting and filters.
- Sort results by real-time estimated premium descending by default, with official-NAV premium available as a secondary metric.
- Show liquidity, subscription status, redemption status, and fee-adjusted opportunity space.
- Clearly distinguish normal data, missing NAV, stale NAV, invalid code, and network/API errors.
- Provide a Streamlit dashboard for daily monitoring and a CLI path for smoke testing.
- Keep the tool small enough to run locally without a database or account setup.
- Keep official-NAV premium and real-time IOPV premium as separate metrics.
- Send threshold alerts to Enterprise WeChat through a configurable robot webhook.

## Non-Goals

- No trading automation.
- No investment advice or buy/sell recommendations.
- No broad ETF universe scanning in the MVP; ETF support starts with explicitly configured ETF products.
- No full historical charting in the first version.
- No account login, portfolio tracking, or brokerage integration.
- No server deployment requirements in the first version.
- No claim that real-time foreign-market estimates exactly match fund holdings or official IOPV.

## Data Sources

### Breadth Source: Jisilu LOF Table

Jisilu's LOF table is the preferred breadth source for scanning many LOF funds because it commonly exposes fields such as code, name, market price, premium/discount rate, turnover, and subscription status in one view.

Implementation notes:

- Treat the exact URL, request parameters, response shape, and required headers/cookies as adapter details because they may change.
- Use low-frequency polling, defaulting to 10-30 seconds only during trading hours.
- If the endpoint requires cookies or becomes unstable, keep the adapter isolated and fall back to narrower quote providers for configured funds.
- Do not hardcode private cookies into source files or committed config.

### Configured ETF Source

ETF support starts as configured-product monitoring rather than broad ETF scanning. ETF rows can use the same quote, IOPV, turnover, fee, and alert logic, but provider adapters must account for ETF-specific fields:

- Creation/redemption status may differ from LOF subscription/redemption status.
- Some ETFs expose exchange IOPV or indicative NAV directly; when available and fresh, prefer official IOPV over a proxy estimate.
- QDII and commodity ETFs may still need foreign-market proxy and FX adjustment.
- ETF minimum creation/redemption units are often unsuitable for small accounts, so the UI should label ETF rows as monitoring references unless the user configures them as actionable.

### Quote Source: Tencent Finance

Tencent Finance `qt.gtimg.cn` remains useful for configured fund-level quote and NAV details because one request can return several fields:

- Listed market price: field `3`
- Premium rate: field `77`
- NAV: field `81`
- Fund name: field `1`
- Fund code: field `2`
- Change percentage: currently parsed from field `32`
- Volume: currently parsed from field `6`

Request format:

```text
https://qt.gtimg.cn/q=sz164701,sz161116,sz161129
```

### Backup Source: Eastmoney Fund API

Eastmoney `api.fund.eastmoney.com/f10/lsjz` is used as a backup NAV source, especially when Tencent returns a missing or suspicious NAV.

It is not the first source for real-time listed price. In the first version, it is used only to fill or verify NAV and NAV date for records that Tencent can identify. If Tencent cannot identify a fund at all, the record remains `invalid_code` rather than silently turning into a NAV-only result.

### Optional Backup Source: Sina Finance

Sina Finance can be added later as a backup listed-price source. It is not part of the first implementation because it has stronger anti-scraping behavior and does not return all required fields in one stable response.

### Core Estimate Source: Foreign Markets And FX (Verified)

For QDII and commodity-linked funds, the official NAV can lag the real market by one or two days. The tool calculates real-time reference NAV (IOPV) using:

- **Foreign futures via Tencent Finance** (`qt.gtimg.cn`): gold (`hf_GC`), WTI crude (`hf_CL`), Brent crude (`hf_OIL`), S&P 500 (`hf_ES`). Returns current price and previous close in a single HTTP GET. Verified working, no rate limiting. Field 0 = current price, field 7 = previous close.
- **USD/CNH real-time via ExchangeRate API** (`open.er-api.com/v6/latest/USD`): returns `rates.CNH`. Free, no auth required.
- **T-1 FX mid-rate via AkShare** (`currency_boc_sina(symbol="美元")`): Bank of China daily mid-rate. Returns values in units of 100 USD, divide by 100 for rate.

**Verified unavailable from this network**:
- Yahoo Finance (`query1.finance.yahoo.com`): SSL error, blocked.
- East Money push2 for foreign futures: frequent connection drops.
- Sina Finance (`hq.sinajs.cn`): HTTP 403 for foreign futures and FX.

Formula:

```text
IOPV = T-1 NAV × (foreign_current / foreign_prev_close) × (fx_current / fx_base)
IOPV premium = (market_price / IOPV - 1) × 100%
```

This is not a replacement for official NAV. It is a separate estimated metric that helps explain intraday premium changes, especially for oil and gold QDII funds where official NAV can lag by 2-3 days.

## Architecture

The design is split into a small core plus presentation layers:

```text
moon/
├── monitor.py          # 核心数据模型、基金数据获取、IOPV 集成
├── estimates.py        # IOPV 估算引擎（外盘+汇率修正）
├── cli.py              # CLI 终端工具（Rich 表格）
├── web.py              # Flask Web 仪表板
├── templates/
│   └── dashboard.html  # Web 前端（深色主题，IOPV 切换）
├── requirements.txt
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-30-lof-qdii-premium-monitor-design.md
```

`monitor.py` owns the domain model, premium calculation, sorting, and high-level fetch API. It integrates IOPV estimation by calling `estimates.py`.

`estimates.py` owns the IOPV estimation engine: foreign futures data fetching (Tencent `hf_*`), FX rate fetching (ExchangeRate API + AkShare BOC), and the IOPV calculation formula. It caches data within a refresh cycle to avoid redundant API calls.

`cli.py` owns command-line arguments, Rich table output, watch mode, alert highlighting, and the `--estimate` flag for IOPV display.

`streamlit_app.py` owns the local dashboard, table filters, refresh controls, and visual highlighting.

`estimates.py` owns foreign-market proxy and FX-based IOPV calculation. It should depend on normalized `FundData` records and fund configuration rather than calling presentation-layer code.

`notifier.py` owns outbound alert delivery. The first notification channel is Enterprise WeChat robot webhook.

## Data Model

`FundData` should represent both successful and partial data:

```python
@dataclass
class FundData:
    code: str
    name: str
    product_type: str
    market_price: float | None
    nav: float | None
    nav_date: str | None
    premium_rate: float | None
    official_nav_premium_rate: float | None
    estimated_iopv: float | None
    estimated_iopv_premium_rate: float | None
    calculated_premium_rate: float | None
    raw_premium_rate: float | None
    change_pct: float | None
    volume: int | None
    turnover_amount: float | None
    subscription_status: str | None
    redemption_status: str | None
    creation_status: str | None
    estimated_fee_rate: float | None
    net_opportunity_rate: float | None
    nav_age_days: int | None
    source: str
    status: str
    message: str | None = None
```

Allowed `status` values:

- `ok`: all important fields are usable.
- `stale_nav`: NAV exists but is older than expected.
- `nav_missing`: price exists but NAV is unavailable.
- `invalid_code`: API returned no usable record for the requested code.
- `source_error`: network timeout, response error, or parse failure.
- `data_mismatch`: API premium rate and locally calculated premium differ beyond tolerance.
- `estimate_unavailable`: official data is usable, but real-time IOPV cannot be calculated.
- `subscription_blocked`: premium opportunity exists but subscription is paused, limited, or unknown.
- `redemption_blocked`: discount opportunity exists but redemption is paused or unknown.
- `creation_blocked`: ETF premium opportunity exists but creation is paused, limited, or not actionable for the configured account.
- `illiquid`: premium or discount is large enough, but turnover is below the configured liquidity threshold.

The display layer should show `message` for partial or failed records instead of raising uncaught exceptions.

## Market Prefix Handling

Fund symbols are normalized through one function:

```python
infer_market_prefix(code: str) -> str
```

Rules:

- If the user passes `sz161129` or `sh513500`, preserve the explicit market prefix.
- `16xxxx` and `15xxxx` default to `sz`.
- `5xxxxx` defaults to `sh`.
- Other six-digit codes default to `sz` but receive a warning message if the API lookup fails.

This keeps the first version simple while allowing explicit-market LOF code handling later.

## Premium Calculation

The tool should not blindly trust the source premium field. For every record with both `market_price` and `nav`, calculate:

```text
calculated_premium_rate = (market_price - nav) / nav * 100
```

Resolution rule:

- If Tencent returns `raw_premium_rate`, use it as `official_nav_premium_rate`.
- If Tencent does not return `raw_premium_rate`, use `calculated_premium_rate` as `official_nav_premium_rate`.
- If both exist and differ by more than `0.2` percentage points, set status to `data_mismatch` and keep both values available for debugging.

`premium_rate` is the default display and sorting metric. For funds with valid IOPV configuration and usable proxy/FX data, it equals `estimated_iopv_premium_rate`. For funds without IOPV configuration or with unavailable estimate data, it falls back to `official_nav_premium_rate`. Funds without any usable premium rate are placed at the bottom.

`official_nav_premium_rate` is the premium against official NAV. `estimated_iopv_premium_rate` is the premium against live real-time reference NAV.

## Arbitrage Opportunity Model

The monitor is not an order system, but it should estimate whether a visible discount/premium is large enough to deserve manual attention after fees and liquidity constraints. LOF remains the primary actionable workflow. ETF rows are supported, but the user must configure whether ETF creation/redemption is actionable for their account.

Direction:

- LOF premium opportunity: market price is above NAV or IOPV. The manual workflow is cash subscription before the deadline, then sell listed shares after they arrive.
- LOF discount opportunity: market price is below NAV or IOPV. The manual workflow is buy listed shares, then redeem if redemption is open and the holding-period fee does not destroy the spread.
- ETF premium opportunity: market price is above IOPV. Creation/redemption mechanics and minimum units vary; treat it as actionable only when the product config says creation is available for the account.
- ETF discount opportunity: market price is below IOPV. Treat it as actionable only when ETF redemption is available and fee/slippage assumptions are configured.

Core opportunity formulas:

```text
gross_premium_rate = (market_price / reference_value - 1) * 100
premium_net_space = gross_premium_rate - subscription_fee_rate - sell_commission_rate - slippage_buffer
discount_net_space = abs(gross_premium_rate) - buy_commission_rate - redemption_fee_rate - slippage_buffer
```

`reference_value` should be real-time IOPV when available, otherwise latest official NAV.

Default filters:

- Absolute gross premium/discount threshold: `1.5%`.
- Minimum turnover amount: `500` 万 CNY.
- LOF premium side requires subscription status to be open or limit-open.
- LOF discount side requires redemption status to be open.
- ETF opportunities require creation/redemption status to be open and account actionability to be explicitly configured.
- Net opportunity must be positive after fee assumptions and slippage buffer.

Fee assumptions should be configurable because brokers and funds differ:

```json
{
  "subscription_fee_rate": 0.15,
  "redemption_fee_rate": 1.5,
  "buy_commission_rate": 0.025,
  "sell_commission_rate": 0.025,
  "slippage_buffer": 0.2,
  "min_turnover_wan": 500,
  "gross_threshold": 1.5,
  "net_threshold": 0.5
}
```

Rates are percentage values. These assumptions are only for screening; the user must verify actual fund and broker fees before acting.

## Real-Time Reference NAV

Real-time reference NAV is the core metric for funds such as oil, gold, and overseas equity QDII products where official NAV lags the live underlying market.

Formula:

```text
estimated_iopv = t_minus_1_nav * foreign_proxy_factor * fx_factor
foreign_proxy_factor = foreign_current / foreign_base_close
fx_factor = current_fx / t_minus_1_fx
estimated_iopv_premium_rate = (market_price / estimated_iopv - 1) * 100
```

Required per-fund configuration:

```json
{
  "code": "161129",
  "estimate_type": "OIL",
  "t_minus_1_nav": 1.245,
  "t_minus_1_nav_date": "2026-04-29",
  "t_minus_1_fx": 7.21,
  "foreign_proxy": "BZ=F",
  "foreign_base_close": 82.5
}
```

Initial proxy mapping:

- `OIL`: Brent crude futures proxy, for example `BZ=F`.
- `GOLD`: international gold futures proxy, for example `GC=F`.
- `NASDAQ`: Nasdaq 100 futures proxy, for example `NQ=F`.

Important limitations:

- Proxy futures may not match the exact fund holdings. For example, an oil LOF may hold overseas oil ETFs rather than Brent futures directly.
- Some ETFs provide official intraday IOPV. Prefer official IOPV over proxy estimates when it is available and fresh.
- Some gold funds track domestic gold assets while others track overseas gold assets. Domestic gold products may need Shanghai gold data instead of international futures.
- Real-time FX can materially move QDII fair value and should be included when the fund is USD-linked.
- This estimate is a monitoring aid, not official NAV and not a trading signal.

Implementation guidance:

- Enable IOPV calculation automatically for funds with complete estimate configuration.
- Show both official NAV premium and real-time IOPV premium.
- Label estimated values clearly as `实时估值(IOPV)` or `estimated_iopv`.
- If proxy or FX data fails, keep official NAV premium visible and mark the estimate as unavailable.
- Cache foreign proxy and FX requests during one refresh cycle so multiple funds sharing the same proxy do not trigger repeated calls.

## NAV Freshness

QDII NAV often lags by one or two business days. The tool should show the NAV date clearly and compute `nav_age_days` when the date is available.

Tencent quote timestamps must not be displayed as NAV dates. If Tencent returns NAV but not a reliable NAV date, the normalizer should query Eastmoney for the latest NAV date. If that fallback also fails, show the NAV value with `nav_date=None` and a message explaining that the NAV date is unavailable.

First-version freshness rule:

- `0-2` calendar days old: acceptable.
- `3+` calendar days old: mark `stale_nav`.
- Missing NAV: mark `nav_missing`.

This is deliberately simple. A later version can use China exchange holidays and fund-specific QDII calendars.

## CLI Design

Command examples:

```bash
python cli.py 164701 161116 161129
python cli.py --config funds.example.json
python cli.py 164701 161116 161129 --watch 30
python cli.py 164701 161116 161129 --alert 5
```

Behavior:

- If codes are passed as arguments, fetch those codes.
- If no codes are passed, prompt for comma- or space-separated input.
- If `--config` is passed, load codes from JSON.
- Sort rows by premium rate descending.
- Render with Rich.
- In watch mode, clear and redraw the table every interval.
- Show a compact timestamp for each refresh.
- During likely non-trading hours, show a note that listed prices may be stale.

Color rules:

- Premium `> alert threshold`: bold red.
- Premium `> 5%`: red.
- Premium `2%` to `5%`: yellow.
- Premium `< 0%`: green.
- Missing or invalid premium: dim.

The default alert threshold is only used for highlighting, not for notifications.

## Alerting And Notifications

The tool supports Enterprise WeChat robot notifications for high-premium or abnormal conditions.

Configuration:

- Webhook URL should be read from `WECHAT_WEBHOOK_URL`.
- The full webhook URL must not be hardcoded into source files, committed config, or documentation.
- Local examples should use a placeholder value such as `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=REPLACE_ME`.

Trigger rules:

- Official NAV premium exceeds `alert_premium`.
- Real-time IOPV premium exceeds `estimate_alert_premium` for funds with IOPV configuration.
- Fee-adjusted net opportunity exceeds `net_alert_premium`.
- Large gross opportunity is blocked by subscription, creation, or redemption status, so the user knows the apparent opportunity may not be actionable.
- `data_mismatch` occurs between source premium and locally calculated premium.
- A previously healthy watched fund moves into `source_error`, `nav_missing`, or `estimate_unavailable`.

Notification behavior:

- Send one Markdown message per refresh cycle summarizing all triggered funds.
- Include product type, code, name, market price, reference value, official premium, IOPV premium, net opportunity, turnover, subscription/creation/redemption status, data status, and refresh timestamp.
- Apply a cooldown per fund and alert type, defaulting to 10 minutes, to avoid repeated messages on every refresh.
- If webhook delivery fails, show a warning in CLI/Web output but do not abort monitoring.

Enterprise WeChat request format:

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "### 场内基金折溢价告警\n..."
  }
}
```

The user-provided webhook key should be treated as a secret. If it has been shared in a chat or committed by mistake, rotate it in Enterprise WeChat and update the local environment variable.

## Streamlit Dashboard Design

The first browser UI is a local Streamlit dashboard because this is mainly a personal monitoring screen.

Dashboard behavior:

- Show a table sorted by default opportunity metric.
- Allow filters for gross premium/discount, net opportunity, turnover, and status.
- Support selecting premium side, discount side, or both.
- Support product-type filters, defaulting to LOF and allowing configured ETFs.
- Show official NAV premium and IOPV premium side by side.
- Highlight rows that exceed alert thresholds.
- Display stale data, blocked subscription/redemption, and source errors as visible status badges.
- Allow refresh interval control, defaulting to 10-30 seconds.

The first version can recompute one refresh per Streamlit rerun. It should avoid an infinite `while True` loop inside the page. Use a controlled auto-refresh mechanism or a timestamp-based refresh button so the app remains responsive.

The Streamlit app should remain a display layer. Fetching, filtering, IOPV calculation, fee modeling, and notification decisions stay in the core modules so they can also be tested from CLI.

## Error Handling

External requests should use:

- Timeout: 10 seconds.
- Retries: 2 attempts for transient network errors.
- Source-specific parse errors converted into `FundData(status="source_error")`.

Invalid or empty records should not abort the whole batch. One failed fund should appear as a row with `status` and `message`.

If the primary Tencent source fails for a full request, the first version returns source errors for all requested funds. A later version can combine Sina price plus Eastmoney NAV as a true fallback path.

## Configuration

Add `funds.example.json`:

```json
{
  "codes": ["164701", "161116", "161129"],
  "default_product_types": ["LOF"],
  "refresh_seconds": 30,
  "alert_premium": 5,
  "estimate_alert_premium": 3,
  "net_alert_premium": 0.5,
  "min_turnover_wan": 500,
  "gross_threshold": 1.5,
  "wechat_cooldown_minutes": 10
}
```

The CLI may accept a custom config path. If no config is passed, command-line codes take precedence. The Streamlit dashboard can use config defaults plus sidebar filters.

Real-time IOPV requires richer per-fund config. This should live in a separate config file or an expanded schema rather than overloading the simple code list.

Secret values such as Enterprise WeChat webhook URLs should be supplied through environment variables or a local untracked `.env` file, not through `funds.example.json`.

## Requirements

Runtime dependencies:

```text
requests
rich
streamlit
pandas
```

`streamlit` and `pandas` are required for the local dashboard.

IOPV dependencies:

```text
akshare
yfinance
```

These are required for real-time IOPV mode. The official-NAV-only fallback can still run without them, but QDII/commodity monitoring should install them.

## Testing And Verification

Unit tests should cover:

- Tencent line parsing for normal records.
- Missing NAV handling.
- Missing premium handling with local calculation fallback.
- Premium mismatch detection.
- Invalid code handling.
- Market prefix inference.
- Sorting with missing premium values.
- Jisilu LOF row normalization for price, turnover, premium, and subscription/redemption status.
- Configured ETF row normalization for product type, IOPV, turnover, and creation/redemption status.
- Estimated IOPV calculation from fixed T-1 NAV, proxy factor, and FX factor.
- Fee-adjusted net opportunity calculation for premium and discount directions.
- Liquidity and subscription/redemption filter behavior.
- Estimate-unavailable behavior when proxy or FX data is missing.
- Enterprise WeChat notification payload formatting.
- Notification cooldown suppression.

Manual smoke tests:

```bash
python cli.py 164701 161116 161129
python cli.py 164701 161116 161129 --watch 30
streamlit run streamlit_app.py
```

Manual verification points:

- Premium rate matches the source page within tolerance.
- QDII NAV date is visible and stale NAV is marked.
- Invalid code produces a friendly row-level message.
- Watch mode refreshes without accumulating duplicate output.
- Streamlit dashboard refreshes without blocking interaction.
- Liquidity, fee-adjusted net space, and subscription/redemption status filters behave as expected.

## Implementation Sequence

1. Refactor external API parsing into `providers.py`.
2. Add Jisilu LOF breadth adapter and normalized row mapping.
3. Add configured ETF adapter support for explicitly listed ETF products.
4. Expand `FundData` with product type, status, source, raw/calculated premium, NAV age, IOPV, liquidity, status, and fee fields.
5. Add fund configuration for product type, T-1 NAV, T-1 FX, foreign proxy, foreign base close, fees, liquidity, actionability, and thresholds.
6. Add real-time IOPV calculation for configured funds.
7. Add fee-adjusted opportunity calculation and actionable/blocking status classification.
8. Update `monitor.py` to normalize records, calculate both premium metrics, validate mismatch, and sort by default opportunity.
9. Create `cli.py` with Rich table rendering, arguments, config loading, watch mode, and alert highlighting.
10. Add `requirements.txt` and `funds.example.json`.
11. Create `streamlit_app.py`.
12. Add focused parser, premium, IOPV, fee, filter, and notification tests.
13. Run real API smoke tests with `164701`, `161116`, and `161129`.
14. Add Enterprise WeChat alert delivery through `WECHAT_WEBHOOK_URL`.

## Deferred Choices

- True fallback combining Sina listed price and Eastmoney NAV is deferred.
- Trading-day-aware `nav_age_days` is deferred; the first version uses calendar days.
- Server-side dashboard watchlist persistence is deferred; the first version reads local config and uses sidebar filters.
- Automatic daily refresh of T-1 NAV, T-1 FX, and foreign base close for estimated IOPV is deferred until the manual estimate path is verified.
