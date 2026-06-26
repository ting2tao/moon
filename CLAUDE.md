# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LOF/QDII 基金溢价监控工具 — monitors premium/discount rates for Chinese exchange-listed LOF and QDII funds. Core feature: IOPV (Indicative Optimized Portfolio Value) estimation using foreign futures prices and real-time FX rates to correct for T-1 NAV lag in QDII funds. Goal: identify arbitrage opportunities when market price deviates from estimated fair value.

## Commands

```bash
# Install dependencies
make install          # or: pip install -r requirements.txt

# Run tests
make test             # or: python -m unittest discover -s tests -p 'test_*.py' -v

# CLI: basic premium monitoring
make cli ARGS="164701 161116 161129"

# CLI: with IOPV estimation (foreign futures + FX correction)
python cli.py 164701 161116 161129 --estimate

# CLI: watch mode with 30s refresh
python cli.py 164701 161116 161129 --estimate --watch 30

# CLI: alert highlighting for premiums above threshold
python cli.py 164701 161116 --alert 5

# CLI: with WeChat push notifications
python cli.py 164701 161116 --estimate --notify

# Streamlit web dashboard (primary)
make web              # or: streamlit run streamlit_app.py --server.port 8502

# Legacy Flask API/dashboard
python web.py
python web.py --estimate --port 5000
```

## Architecture

**Data flow**: External APIs → `monitor.py` → `estimates.py` → `arbitrage.py` → CLI/Web display

### Core modules

- **`monitor.py`** — Data layer. `FundData` dataclass (47 fields). `_parse_tencent_line()` parses Tencent Finance `~`-delimited lines (index 1=name, 2=code, 3=price, 6=volume, 30=datetime, 32=change%, 77=premium%, 81=NAV). `fetch_fund_data()` batch-fetches quotes and subscription status (Eastmoney mobile API). `enrich_with_iopv()` integrates IOPV from `estimates.py`. `apply_opportunity_metrics()` populates premium, reference value, net opportunity, direction, status, and data quality.

- **`estimates.py`** — IOPV estimation engine. `FundEstimateConfig` dataclass maps fund code → foreign proxy ticker + FX pair. `FUND_CONFIGS` dict holds 25 known configs (gold, silver, WTI/Brent oil, S&P 500, NASDAQ, Hang Seng, India, KWEB). `estimate_iopv()` core formula. `fetch_foreign_quotes()` calls Tencent `hf_*` endpoints (field 0=price, 7=prev_close). `fetch_fx_rate()` gets real-time USD/CNH + T-1 BOC mid-rate. `fetch_estimated_nav()` from Tiantian Fund. Module-level caches (`_foreign_cache`, `_fx_cache`, `_estimated_nav_cache`) deduplicate per refresh cycle. Precision grades: A (est NAV + BOC mid-rate), B (est NAV + realtime FX), C (official NAV), D (missing). `auto_detect_config()` infers fund type from Chinese keywords.

- **`arbitrage.py`** — Pure calculation (no I/O). `OpportunityConfig` with fee rates. `calculate_official_premium()`, `choose_reference_value()` (prefers IOPV over official NAV), `calculate_net_opportunity()` (deducts fees), `classify_status()` (actionable/watch_only/subscription_blocked/redemption_blocked/creation_blocked/illiquid/source_error), `score_data_quality()` (A/B/C/D).

- **`providers.py`** — Market prefix inference (`sz` for 16xxxx/15xxxx, `sh` for 5xxxxx), code normalization, percent/float parsing.

### Presentation modules

- **`cli.py`** — Rich terminal table. Flags: `--estimate`, `--watch N`, `--alert N`, `--notify`. `alert_rows()` filters actionable opportunities above thresholds. `filter_rows_by_cooldown()` deduplicates alerts.

- **`streamlit_app.py`** — Primary web dashboard. Sidebar controls for fund codes, IOPV toggle, thresholds, product type filter, actionable-only toggle. 15-second `@st.cache_data(ttl=15)` caching. WeChat notification from UI.

- **`web.py`** — Legacy Flask API (backward compat). Endpoints: `GET /api/funds`, `GET /api/alerts`, `POST /api/notify`, `GET/POST /api/config`, `POST /api/funds/add`, `POST /api/funds/remove`, `GET /api/sources`. Serves `templates/dashboard.html`.

- **`notifier.py`** — Enterprise WeChat webhook. `format_alert_markdown()` builds content. `WeChatNotifier.send_markdown()` posts to `WECHAT_WEBHOOK_URL` env var. `AlertCooldown` deduplicates (default 600s window).

### Configuration

- **`funds.json`** — Runtime config: fund codes, thresholds (alert_premium 5%, estimate_alert_premium 3%, net_alert_premium 0.5%, gross_threshold 1.5%, min_turnover 500万), WeChat cooldown 10min, refresh interval 30s.

## External APIs

| Data | Endpoint | Key Fields |
|------|----------|------------|
| Fund quotes (price, NAV, premium) | `http://qt.gtimg.cn/q=sz{code}` | `~`-delimited, indices above |
| Foreign futures (gold, oil) | `http://qt.gtimg.cn/q=hf_GC,hf_CL` | comma-delimited, [0]=price, [7]=prev_close |
| Real-time FX | `https://open.er-api.com/v6/latest/USD` | `rates.CNH` |
| T-1 FX mid-rate | `akshare.currency_boc_sina(symbol="美元")` | `央行中间价` / 100 |
| Estimated NAV | `https://fundgz.1234567.com.cn/js/{code}.js` | Real-time IOPV from Tiantian Fund |
| Historical NAV backup | `https://api.fund.eastmoney.com/f10/lsjz` | `Data.LSJZList[].DWJZ` |
| Subscription status | Eastmoney mobile API | Whether fund allows subscribe/redeem |

All HTTP requests use 10s timeout and a browser User-Agent header.

## IOPV Formula

```
IOPV = T-1 NAV × (foreign_current / foreign_prev_close) × (fx_current / fx_base)
IOPV premium = (market_price / IOPV - 1) × 100%
```

Known fund configs are in `estimates.py:FUND_CONFIGS`. New funds need a `FundEstimateConfig` entry with the correct Tencent foreign proxy code (`hf_GC` for gold, `hf_CL` for WTI oil, `hf_OIL` for Brent, `hf_ES` for S&P 500).

## Market Prefix Convention

- `16xxxx`, `15xxxx` → `sz` (Shenzhen)
- `5xxxxx` → `sh` (Shanghai)
