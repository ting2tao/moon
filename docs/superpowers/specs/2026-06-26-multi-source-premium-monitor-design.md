# Multi-Source Premium Monitor Design

## Context

Moon is currently a local LOF/QDII premium monitor. The core flow is:

```text
Tencent fund quotes -> monitor.py -> estimates.py -> arbitrage.py -> cli.py / streamlit_app.py / web.py
```

Existing responsibilities:

- `monitor.py`: `FundData`, Tencent quote parsing, Eastmoney subscription/redemption status, IOPV enrichment, opportunity metrics.
- `estimates.py`: QDII IOPV estimation using foreign proxies and FX.
- `arbitrage.py`: pure premium, fee, status, and data-quality calculations.
- `providers.py`: shared parsing and normalization helpers.
- `cli.py`, `streamlit_app.py`, `web.py`: presentation and alert entry points.

The next step is not to scrape every public finance page. The next step is to make Moon data-source agnostic so official or commercial sources can be added without changing premium logic.

## Goal

Build a multi-source architecture for monitoring premium/discount opportunities across configured products, with clear source contracts, data quality, source attribution, and adapter placeholders for domestic commercial data sources such as iFinD and Choice.

## First-Phase Scope

Phase one is architecture-first:

- Add a unified provider interface for quote, reference value, status, and metadata data.
- Keep existing Tencent, Eastmoney, Tiantian Fund, foreign proxy, and FX logic working.
- Add source registry and source selection policy: primary, fallback, compare-only, disabled.
- Add source attribution to every premium snapshot.
- Add data-quality and freshness checks at source level.
- Add commercial-source placeholders for iFinD and Choice that define credentials, capability shape, and expected outputs, but do not implement undocumented live calls.
- Add tests using fixtures and fake providers so the core monitor does not depend on live APIs.

## Non-Goals

- No automatic trading.
- No investment advice.
- No committed credentials, cookies, tokens, account IDs, or terminal license files.
- No production reliance on undocumented web endpoints for iFinD, Choice, Tonghuashun App, or Eastmoney App.
- No attempt to monitor every global premium type in one implementation pass.
- No database requirement in phase one.

## Premium Types

The architecture should support multiple premium families, but implementation starts with fund NAV/IOPV premiums because Moon already owns that domain.

| Premium family | Phase one support | Reference value | Notes |
| --- | --- | --- | --- |
| LOF/QDII fund premium | Yes | NAV or estimated IOPV | Existing main workflow. |
| ETF premium | Partial | Exchange IOPV or estimated IOPV | Configured products only. |
| A/H premium | Model only | A-share price vs H-share FX-adjusted price | Needs symbol mapping and cross-market quotes. |
| ADR premium | Model only | ADR price vs local share FX/ratio-adjusted price | Needs ADR ratio and FX. |
| Convertible bond premium | Model only | Conversion value | Needs bond terms and stock quote. |

Model-only means the data model and interfaces should not block the future type, but no live adapter is required yet.

## Data Source Matrix

| Source | Phase one role | Production stance | Expected capabilities |
| --- | --- | --- | --- |
| Tencent Finance | Existing primary/fallback | Useful for configured fund quotes; keep isolated | Fund quote, NAV, turnover, premium field. |
| Eastmoney fund APIs | Existing fallback/status | Useful for NAV and fund status; public endpoints are not treated as guaranteed | NAV history, subscription/redemption status. |
| Tiantian Fund estimate | Existing reference input | Useful but must be source-attributed | Estimated NAV. |
| Foreign proxies + FX | Existing reference input | Required for QDII IOPV | Foreign price, previous close, FX current/base. |
| iFinD | Placeholder | Commercial/authorized only | A-share/H-share/fund/ETF/NAV/reference data when licensed. |
| Choice | Placeholder | Commercial/authorized only | A-share/H-share/fund/ETF/NAV/reference data when licensed. |
| Futu/Longbridge/Tiger/IBKR | Later | Authorized broker APIs only | Cross-market quotes and WebSocket refresh. |

## Source Contract

Every provider must return normalized data and source metadata. Provider implementations should not calculate business status directly.

```python
@dataclass(frozen=True)
class SourceMeta:
    source: str
    source_type: str
    entitlement: str
    fetched_at: datetime
    latency_ms: int | None
    freshness_seconds: int | None
    quality: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    market: str
    product_type: str
    last_price: float | None
    bid: float | None
    ask: float | None
    turnover_amount: float | None
    trade_time: datetime | None
    meta: SourceMeta


@dataclass(frozen=True)
class ReferenceSnapshot:
    symbol: str
    reference_type: str
    value: float | None
    reference_time: datetime | None
    meta: SourceMeta
```

Provider capability methods:

```python
class MarketDataProvider(Protocol):
    name: str

    def capabilities(self) -> SourceCapabilities:
        ...

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        ...

    def fetch_references(self, symbols: list[str]) -> list[ReferenceSnapshot]:
        ...

    def fetch_statuses(self, symbols: list[str]) -> list[TradingStatusSnapshot]:
        ...
```

## Source Policy

Source policy belongs in config, not scattered across provider code.

Example:

```json
{
  "sources": {
    "tencent": {"mode": "primary", "timeout_seconds": 10},
    "eastmoney": {"mode": "fallback", "timeout_seconds": 10},
    "tiantian": {"mode": "reference", "timeout_seconds": 10},
    "ifind": {"mode": "disabled"},
    "choice": {"mode": "disabled"}
  },
  "source_compare": {
    "enabled": true,
    "max_price_deviation_pct": 0.3,
    "max_reference_deviation_pct": 0.5
  }
}
```

Modes:

- `primary`: used first for fields it supports.
- `fallback`: used when primary misses or fails.
- `reference`: used only for reference/NAV/IOPV inputs.
- `compare-only`: fetched and compared, but not selected unless manually promoted.
- `disabled`: ignored.

## Data Quality

Quality is source-aware. A premium row can only be actionable if both quote and reference data are good enough.

Quality grades:

- `A`: licensed or known-stable source, fresh quote, fresh reference, no cross-source conflict.
- `B`: fresh quote and reference, but one source is public best-effort or minor cross-source drift exists.
- `C`: stale reference, missing freshness metadata, or only one fragile public source.
- `D`: missing quote/reference, provider error, severe cross-source conflict, or unauthorized source.

Cross-source conflict rules:

- Price conflict: mark row `source_conflict` if selected quote and compare source differ beyond configured threshold.
- Reference conflict: mark row `reference_conflict` if NAV/IOPV sources differ beyond configured threshold.
- Conflict rows must remain visible but should not trigger WeChat alerts.

## Adapter Boundaries

Existing live-call logic should be migrated behind adapters without changing calculation semantics:

- Tencent fund quote adapter wraps current `fetch_fund_data` quote behavior.
- Eastmoney status adapter wraps current subscription/redemption request.
- Tiantian estimate adapter wraps current estimated NAV request.
- Foreign proxy and FX adapters stay owned by `estimates.py` initially, then can be lifted into providers after the interface is stable.
- iFinD and Choice adapters should be explicit stubs that fail closed with `disabled_or_unconfigured`, not silent empty data.

## Commercial Source Placeholders

iFinD and Choice placeholder adapters should define:

- Expected environment variables or config keys.
- Whether a local terminal/session is required.
- Supported markets and product families.
- Expected normalized output fields.
- Clear error state when credentials or SDK modules are missing.

The placeholder must not include guessed endpoint URLs, reverse-engineered requests, or copied proprietary field dictionaries.

## User-Facing Behavior

CLI, Streamlit, and Flask API should expose source status without overwhelming the table:

- Selected quote source.
- Selected reference source.
- Data quality grade.
- Source warning count.
- Conflict status.

Detailed source diagnostics can be shown behind an expanded details view or API field.

## Testing Strategy

Phase one tests should not require network access:

- Fake provider returns valid quote/reference/status snapshots.
- Fallback provider fills missing fields.
- Compare-only provider triggers conflict when deviation is too large.
- Disabled iFinD/Choice providers return explicit configuration errors.
- Existing premium math tests stay unchanged.
- Existing Tencent parsing tests remain as adapter fixture tests.

Live smoke tests are optional and should be separated from unit tests.

## Harness

Agent-visible verification:

- `make test`
- `.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v`
- `.venv/bin/python -m py_compile monitor.py providers.py arbitrage.py estimates.py cli.py streamlit_app.py web.py`
- Optional live smoke: `.venv/bin/python cli.py 164701 161116 161129 --estimate`

Failure diagnostics:

- Provider errors must include source name, capability, symbol count, and safe error summary.
- Source policy decisions must be inspectable from tests without live APIs.
- Conflict rows must carry both selected and compared source names.

## Risks

- Public finance endpoints can change without notice.
- Commercial data APIs require licensing and may prohibit redistribution.
- Too much abstraction can slow down a small tool. The interface must stay narrow and fixture-driven.
- A/H, ADR, and convertible bond premiums require product-specific reference models; they should not be forced through fund-only logic.

## Done Signal

Phase one is done when:

- Existing LOF/QDII monitor behavior remains intact.
- Data fetching is routed through a provider registry or source policy layer.
- Every premium row can report quote source, reference source, quality, and warnings.
- iFinD and Choice adapters exist as disabled/unconfigured placeholders with documented contract.
- Unit tests cover selection, fallback, conflict, disabled commercial providers, and current fund premium workflow.

