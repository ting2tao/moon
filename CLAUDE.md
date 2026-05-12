# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LOF/QDII 基金溢价监控工具 — monitors premium/discount rates for Chinese exchange-listed LOF and QDII funds. Core feature: IOPV (Indicative Optimized Portfolio Value) estimation using foreign futures prices and real-time FX rates to correct for T-1 NAV lag in QDII funds.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# CLI: basic premium monitoring
python cli.py 164701 161116 161129

# CLI: with IOPV estimation (foreign futures + FX correction)
python cli.py 164701 161116 161129 --estimate

# CLI: watch mode with 30s refresh
python cli.py 164701 161116 161129 --estimate --watch 30

# CLI: alert highlighting for premiums above threshold
python cli.py 164701 161116 --alert 5

# Web dashboard
python web.py
python web.py --estimate --port 5000
```

No test suite exists yet.

## Architecture

**Data flow**: `monitor.py` (fund data) → `estimates.py` (IOPV calculation) → `cli.py` / `web.py` (display)

- **`monitor.py`** — `FundData` dataclass, `fetch_fund_data()` (Tencent Finance API), `enrich_with_iopv()` (integrates IOPV into FundData). The `_parse_tencent_line()` parser uses `~`-delimited fields: index 1=name, 2=code, 3=price, 6=volume, 30=datetime, 32=change%, 77=premium%, 81=NAV.

- **`estimates.py`** — IOPV estimation engine. `FUND_CONFIGS` dict maps fund codes to `FundEstimateConfig` (foreign proxy ticker, FX pair). `fetch_foreign_quotes()` calls Tencent `hf_*` endpoints (field 0=current price, field 7=previous close). `fetch_fx_rate()` gets real-time USD/CNH from `open.er-api.com` and T-1 BOC mid-rate via `akshare.currency_boc_sina()`. Results are cached per refresh cycle via module-level `_foreign_cache` and `_fx_cache`.

- **`cli.py`** — Rich table output. `--estimate` flag adds IOPV/IOPV溢价 columns and calls `enrich_with_iopv()`. Sorting uses IOPV premium when estimate mode is active.

- **`web.py`** — Flask app with `GET /api/funds?codes=...&estimate=true` JSON endpoint. Frontend (`templates/dashboard.html`) has an IOPV toggle button that switches between official and IOPV premium columns.

## External APIs

| Data | Endpoint | Key Fields |
|------|----------|------------|
| Fund quotes (price, NAV, premium) | `http://qt.gtimg.cn/q=sz{code}` | `~`-delimited, indices above |
| Foreign futures (gold, oil) | `http://qt.gtimg.cn/q=hf_GC,hf_CL` | comma-delimited, [0]=price, [7]=prev_close |
| Real-time FX | `https://open.er-api.com/v6/latest/USD` | `rates.CNH` |
| T-1 FX mid-rate | `akshare.currency_boc_sina(symbol="美元")` | `央行中间价` / 100 |
| Historical NAV backup | `https://api.fund.eastmoney.com/f10/lsjz` | `Data.LSJZList[].DWJZ` |

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
