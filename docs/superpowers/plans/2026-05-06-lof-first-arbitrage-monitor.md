# LOF-First Arbitrage Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable LOF-first on-exchange fund discount/premium monitor with configured ETF support, IOPV, fee-adjusted opportunity screening, Streamlit dashboard, CLI output, and Enterprise WeChat alerts.

**Architecture:** Keep external data adapters in `providers.py`, pure calculations in `arbitrage.py` and `estimates.py`, notification formatting/sending in `notifier.py`, orchestration in `monitor.py`, and display code in `cli.py` plus `streamlit_app.py`. Tests target pure behavior first so live API instability does not block core verification.

**Tech Stack:** Python standard library, `requests`, `rich`, `streamlit`, `pandas`, optional `akshare`.

---

### Task 1: Core Models And Opportunity Math

**Files:**
- Create: `arbitrage.py`
- Modify: `monitor.py`
- Test: `tests/test_arbitrage.py`

- [ ] Write tests for premium calculation, IOPV fallback sorting metric, fee-adjusted premium/discount net space, and actionable/blocking statuses.
- [ ] Run `python -m unittest tests.test_arbitrage -v` and verify failures are caused by missing `arbitrage.py`.
- [ ] Implement `OpportunityConfig`, `ArbitrageMetrics`, `calculate_official_premium`, `choose_reference_value`, `calculate_net_opportunity`, and `classify_status`.
- [ ] Run `python -m unittest tests.test_arbitrage -v` and verify it passes.

### Task 2: Notification Formatting And Cooldown

**Files:**
- Create: `notifier.py`
- Test: `tests/test_notifier.py`

- [ ] Write tests for Enterprise WeChat markdown payload formatting and cooldown suppression.
- [ ] Run `python -m unittest tests.test_notifier -v` and verify failures are caused by missing `notifier.py`.
- [ ] Implement `WeChatNotifier`, `format_alert_markdown`, and in-memory cooldown state.
- [ ] Run `python -m unittest tests.test_notifier -v` and verify it passes.

### Task 3: Provider Layer And Monitor Orchestration

**Files:**
- Create: `providers.py`
- Modify: `monitor.py`
- Test: `tests/test_providers.py`

- [ ] Write tests for market prefix normalization, Tencent line parsing, and Jisilu row normalization from sample rows.
- [ ] Run `python -m unittest tests.test_providers -v` and verify failures are caused by missing provider functions.
- [ ] Move provider parsing into `providers.py` while preserving current Tencent behavior.
- [ ] Add optional Jisilu row normalization without depending on live Jisilu during tests.
- [ ] Update `monitor.py` to produce enriched `FundData` rows with product type, IOPV premium, net opportunity, and status.
- [ ] Run `python -m unittest tests.test_providers tests.test_arbitrage -v` and verify it passes.

### Task 4: CLI And Streamlit Dashboard

**Files:**
- Modify: `cli.py`
- Create: `streamlit_app.py`
- Modify: `requirements.txt`
- Modify: `funds.json`

- [ ] Update CLI columns to show product type, reference value, default premium, official premium, IOPV premium, net opportunity, turnover, and status.
- [ ] Create Streamlit dashboard with sidebar filters for product type, gross threshold, net threshold, turnover, and refresh seconds.
- [ ] Update requirements from Flask dashboard to Streamlit dashboard dependencies.
- [ ] Keep `web.py` in place for backward compatibility, but do not make it the primary entry point.

### Task 5: Verification

**Files:**
- All changed files

- [ ] Run `python -m unittest discover -v`.
- [ ] Run `python cli.py 164701 161116 161129 --estimate` as a live smoke test. If network is blocked, record the actual error.
- [ ] Run `python -m py_compile monitor.py providers.py arbitrage.py estimates.py notifier.py cli.py streamlit_app.py`.
