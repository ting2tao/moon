# Multi-Source Premium Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider registry and source policy layer so Moon can monitor premiums with source attribution, fallback, quality grading, and commercial-source placeholders for iFinD and Choice.

**Architecture:** Keep premium math in `arbitrage.py`, keep IOPV estimation in `estimates.py`, and move live source access behind narrow provider contracts. The first implementation preserves current Tencent/Eastmoney/Tiantian behavior while adding testable source selection, fallback, conflict detection, and disabled commercial adapters.

**Tech Stack:** Python 3.10+, standard library dataclasses/protocols, `requests`, existing `unittest` suite, no new runtime dependency in phase one.

---

## File Structure

- Create `source_models.py`: normalized source metadata, quote/reference/status snapshots, capability declarations, provider errors.
- Create `source_policy.py`: config parsing, source mode handling, fallback and compare thresholds.
- Create `source_registry.py`: provider registration, quote/reference/status orchestration, fallback, conflict detection.
- Modify `providers.py`: keep existing parsing helpers and add provider factory exports only if needed.
- Modify `monitor.py`: route current fund fetch through registry while preserving `FundData` output.
- Create `commercial_sources.py`: disabled iFinD and Choice provider placeholders.
- Create `tests/test_source_policy.py`: source mode and threshold tests.
- Create `tests/test_source_registry.py`: fake provider fallback and conflict tests.
- Create `tests/test_commercial_sources.py`: iFinD/Choice disabled behavior tests.
- Modify `tests/test_monitor.py`: assert `FundData` carries source attribution and quality.
- Modify `funds.json`: add optional `sources` and `source_compare` config blocks.
- Modify `README.md`: document source policy and commercial-source boundary.

---

### Task 1: Source Models

**Files:**
- Create: `source_models.py`
- Test: `tests/test_source_policy.py`

- [ ] **Step 1: Write source model tests**

Add to `tests/test_source_policy.py`:

```python
import unittest
from datetime import datetime, timezone


class SourceModelTests(unittest.TestCase):
    def test_source_meta_preserves_attribution_and_quality(self):
        from source_models import SourceMeta

        meta = SourceMeta(
            source="fake",
            source_type="public",
            entitlement="public_best_effort",
            fetched_at=datetime(2026, 6, 26, 9, 30, tzinfo=timezone.utc),
            latency_ms=12,
            freshness_seconds=3,
            quality="A",
            warnings=("fixture",),
        )

        self.assertEqual(meta.source, "fake")
        self.assertEqual(meta.quality, "A")
        self.assertEqual(meta.warnings, ("fixture",))

    def test_quote_and_reference_snapshots_hold_source_meta(self):
        from source_models import SourceMeta, QuoteSnapshot, ReferenceSnapshot

        meta = SourceMeta.fixture("fake")
        quote = QuoteSnapshot(
            symbol="161129",
            market="sz",
            product_type="LOF",
            last_price=1.04,
            bid=None,
            ask=None,
            turnover_amount=8_000_000,
            trade_time=None,
            meta=meta,
        )
        reference = ReferenceSnapshot(
            symbol="161129",
            reference_type="nav",
            value=1.0,
            reference_time=None,
            meta=meta,
        )

        self.assertEqual(quote.meta.source, "fake")
        self.assertEqual(reference.value, 1.0)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_source_policy -v
```

Expected: failure with `ModuleNotFoundError: No module named 'source_models'`.

- [ ] **Step 3: Implement source models**

Create `source_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class SourceMeta:
    source: str
    source_type: str
    entitlement: str
    fetched_at: datetime
    latency_ms: int | None = None
    freshness_seconds: int | None = None
    quality: str = "C"
    warnings: tuple[str, ...] = ()

    @classmethod
    def fixture(cls, source: str, quality: str = "A") -> "SourceMeta":
        return cls(
            source=source,
            source_type="fixture",
            entitlement="test",
            fetched_at=datetime.now(timezone.utc),
            quality=quality,
        )


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


@dataclass(frozen=True)
class TradingStatusSnapshot:
    symbol: str
    subscription_status: str | None
    redemption_status: str | None
    creation_status: str | None
    meta: SourceMeta


@dataclass(frozen=True)
class SourceCapabilities:
    quotes: bool = False
    references: bool = False
    statuses: bool = False
    markets: tuple[str, ...] = ()
    product_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderIssue:
    source: str
    capability: str
    message: str


class MarketDataProvider(Protocol):
    name: str

    def capabilities(self) -> SourceCapabilities:
        raise NotImplementedError

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        raise NotImplementedError

    def fetch_references(self, symbols: list[str]) -> list[ReferenceSnapshot]:
        raise NotImplementedError

    def fetch_statuses(self, symbols: list[str]) -> list[TradingStatusSnapshot]:
        raise NotImplementedError
```

- [ ] **Step 4: Verify tests pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_source_policy -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add source_models.py tests/test_source_policy.py
git commit -m "feat(sources): add normalized source models"
```

---

### Task 2: Source Policy

**Files:**
- Create: `source_policy.py`
- Modify: `tests/test_source_policy.py`

- [ ] **Step 1: Add policy tests**

Append to `tests/test_source_policy.py`:

```python
class SourcePolicyTests(unittest.TestCase):
    def test_builds_default_policy(self):
        from source_policy import SourcePolicy

        policy = SourcePolicy.from_mapping({})

        self.assertEqual(policy.mode_for("tencent"), "primary")
        self.assertEqual(policy.mode_for("eastmoney"), "fallback")
        self.assertTrue(policy.compare_enabled)

    def test_respects_disabled_and_compare_only_modes(self):
        from source_policy import SourcePolicy

        policy = SourcePolicy.from_mapping(
            {
                "sources": {
                    "ifind": {"mode": "disabled"},
                    "choice": {"mode": "compare-only"},
                },
                "source_compare": {
                    "enabled": True,
                    "max_price_deviation_pct": 0.2,
                    "max_reference_deviation_pct": 0.4,
                },
            }
        )

        self.assertEqual(policy.mode_for("ifind"), "disabled")
        self.assertEqual(policy.mode_for("choice"), "compare-only")
        self.assertEqual(policy.max_price_deviation_pct, 0.2)
        self.assertEqual(policy.max_reference_deviation_pct, 0.4)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_source_policy -v
```

Expected: failure with `ModuleNotFoundError: No module named 'source_policy'`.

- [ ] **Step 3: Implement source policy**

Create `source_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SOURCE_MODES = {
    "tencent": "primary",
    "eastmoney": "fallback",
    "tiantian": "reference",
    "ifind": "disabled",
    "choice": "disabled",
}

ALLOWED_MODES = {"primary", "fallback", "reference", "compare-only", "disabled"}


@dataclass(frozen=True)
class SourcePolicy:
    source_modes: dict[str, str]
    compare_enabled: bool = True
    max_price_deviation_pct: float = 0.3
    max_reference_deviation_pct: float = 0.5

    @classmethod
    def from_mapping(cls, values: dict | None) -> "SourcePolicy":
        values = values or {}
        configured_sources = values.get("sources") or {}
        modes = dict(DEFAULT_SOURCE_MODES)
        for source, config in configured_sources.items():
            mode = (config or {}).get("mode", modes.get(source, "disabled"))
            if mode not in ALLOWED_MODES:
                raise ValueError(f"unsupported source mode for {source}: {mode}")
            modes[source] = mode

        compare = values.get("source_compare") or {}
        return cls(
            source_modes=modes,
            compare_enabled=bool(compare.get("enabled", True)),
            max_price_deviation_pct=float(compare.get("max_price_deviation_pct", 0.3)),
            max_reference_deviation_pct=float(compare.get("max_reference_deviation_pct", 0.5)),
        )

    def mode_for(self, source: str) -> str:
        return self.source_modes.get(source, "disabled")

    def enabled_sources(self) -> list[str]:
        return [name for name, mode in self.source_modes.items() if mode != "disabled"]
```

- [ ] **Step 4: Verify tests pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_source_policy -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add source_policy.py tests/test_source_policy.py
git commit -m "feat(sources): add source policy"
```

---

### Task 3: Registry Selection, Fallback, And Conflict

**Files:**
- Create: `source_registry.py`
- Create: `tests/test_source_registry.py`

- [ ] **Step 1: Write registry tests**

Create `tests/test_source_registry.py`:

```python
import unittest


class FakeQuoteProvider:
    def __init__(self, name, price, mode_quality="A"):
        from source_models import SourceCapabilities

        self.name = name
        self.price = price
        self._capabilities = SourceCapabilities(quotes=True, markets=("cn",), product_types=("LOF",))
        self.mode_quality = mode_quality

    def capabilities(self):
        return self._capabilities

    def fetch_quotes(self, symbols):
        from source_models import QuoteSnapshot, SourceMeta

        if self.price is None:
            return []
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                market="sz",
                product_type="LOF",
                last_price=self.price,
                bid=None,
                ask=None,
                turnover_amount=8_000_000,
                trade_time=None,
                meta=SourceMeta.fixture(self.name, self.mode_quality),
            )
        ]

    def fetch_references(self, symbols):
        return []

    def fetch_statuses(self, symbols):
        return []


class SourceRegistryTests(unittest.TestCase):
    def test_falls_back_when_primary_has_no_quote(self):
        from source_policy import SourcePolicy
        from source_registry import SourceRegistry

        registry = SourceRegistry(
            [FakeQuoteProvider("primary", None), FakeQuoteProvider("fallback", 1.23)],
            SourcePolicy.from_mapping(
                {
                    "sources": {
                        "primary": {"mode": "primary"},
                        "fallback": {"mode": "fallback"},
                    }
                }
            ),
        )

        result = registry.fetch_best_quotes(["161129"])

        self.assertEqual(result["161129"].last_price, 1.23)
        self.assertEqual(result["161129"].meta.source, "fallback")

    def test_marks_conflict_when_compare_source_deviates(self):
        from source_policy import SourcePolicy
        from source_registry import SourceRegistry

        registry = SourceRegistry(
            [FakeQuoteProvider("primary", 1.00), FakeQuoteProvider("compare", 1.02)],
            SourcePolicy.from_mapping(
                {
                    "sources": {
                        "primary": {"mode": "primary"},
                        "compare": {"mode": "compare-only"},
                    },
                    "source_compare": {"enabled": True, "max_price_deviation_pct": 0.3},
                }
            ),
        )

        result = registry.fetch_best_quotes(["161129"])

        self.assertEqual(result["161129"].meta.source, "primary")
        self.assertIn("source_conflict:compare", result["161129"].meta.warnings)
        self.assertEqual(result["161129"].meta.quality, "D")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_source_registry -v
```

Expected: failure with `ModuleNotFoundError: No module named 'source_registry'`.

- [ ] **Step 3: Implement source registry**

Create `source_registry.py`:

```python
from __future__ import annotations

from dataclasses import replace

from source_models import MarketDataProvider, QuoteSnapshot, SourceMeta
from source_policy import SourcePolicy


def _deviation_pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a <= 0:
        return None
    return abs(b / a - 1) * 100


def _with_warning(meta: SourceMeta, warning: str, quality: str | None = None) -> SourceMeta:
    warnings = tuple(dict.fromkeys((*meta.warnings, warning)))
    return replace(meta, warnings=warnings, quality=quality or meta.quality)


class SourceRegistry:
    def __init__(self, providers: list[MarketDataProvider], policy: SourcePolicy):
        self.providers = {provider.name: provider for provider in providers}
        self.policy = policy

    def _providers_by_mode(self, modes: tuple[str, ...]) -> list[MarketDataProvider]:
        selected = []
        for name, provider in self.providers.items():
            if self.policy.mode_for(name) in modes:
                selected.append(provider)
        return selected

    def fetch_best_quotes(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        selected: dict[str, QuoteSnapshot] = {}

        for provider in self._providers_by_mode(("primary", "fallback")):
            for quote in provider.fetch_quotes(symbols):
                if quote.symbol not in selected and quote.last_price is not None:
                    selected[quote.symbol] = quote

        if self.policy.compare_enabled:
            for provider in self._providers_by_mode(("compare-only",)):
                for quote in provider.fetch_quotes(symbols):
                    selected_quote = selected.get(quote.symbol)
                    if selected_quote is None:
                        continue
                    deviation = _deviation_pct(selected_quote.last_price, quote.last_price)
                    if deviation is not None and deviation > self.policy.max_price_deviation_pct:
                        selected[quote.symbol] = replace(
                            selected_quote,
                            meta=_with_warning(
                                selected_quote.meta,
                                f"source_conflict:{quote.meta.source}",
                                quality="D",
                            ),
                        )

        return selected
```

- [ ] **Step 4: Verify tests pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_source_registry -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add source_registry.py tests/test_source_registry.py
git commit -m "feat(sources): add source registry fallback"
```

---

### Task 4: Commercial Source Placeholders

**Files:**
- Create: `commercial_sources.py`
- Create: `tests/test_commercial_sources.py`

- [ ] **Step 1: Write placeholder tests**

Create `tests/test_commercial_sources.py`:

```python
import unittest


class CommercialSourceTests(unittest.TestCase):
    def test_ifind_placeholder_is_disabled_without_credentials(self):
        from commercial_sources import IFindProvider

        provider = IFindProvider(enabled=False)

        self.assertEqual(provider.name, "ifind")
        self.assertFalse(provider.capabilities().quotes)
        self.assertEqual(provider.fetch_quotes(["161129"]), [])
        self.assertEqual(provider.last_error, "disabled_or_unconfigured")

    def test_choice_placeholder_is_disabled_without_credentials(self):
        from commercial_sources import ChoiceProvider

        provider = ChoiceProvider(enabled=False)

        self.assertEqual(provider.name, "choice")
        self.assertFalse(provider.capabilities().quotes)
        self.assertEqual(provider.fetch_references(["161129"]), [])
        self.assertEqual(provider.last_error, "disabled_or_unconfigured")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_commercial_sources -v
```

Expected: failure with `ModuleNotFoundError: No module named 'commercial_sources'`.

- [ ] **Step 3: Implement disabled placeholders**

Create `commercial_sources.py`:

```python
from __future__ import annotations

from source_models import QuoteSnapshot, ReferenceSnapshot, SourceCapabilities, TradingStatusSnapshot


class _DisabledCommercialProvider:
    name = "commercial"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.last_error: str | None = None

    def capabilities(self) -> SourceCapabilities:
        if not self.enabled:
            return SourceCapabilities()
        return SourceCapabilities(
            quotes=True,
            references=True,
            statuses=True,
            markets=("cn", "hk", "us"),
            product_types=("LOF", "ETF", "STOCK", "BOND"),
        )

    def _disabled(self):
        if not self.enabled:
            self.last_error = "disabled_or_unconfigured"
            return True
        return False

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        if self._disabled():
            return []
        raise NotImplementedError(f"{self.name} live adapter requires licensed SDK wiring")

    def fetch_references(self, symbols: list[str]) -> list[ReferenceSnapshot]:
        if self._disabled():
            return []
        raise NotImplementedError(f"{self.name} live adapter requires licensed SDK wiring")

    def fetch_statuses(self, symbols: list[str]) -> list[TradingStatusSnapshot]:
        if self._disabled():
            return []
        raise NotImplementedError(f"{self.name} live adapter requires licensed SDK wiring")


class IFindProvider(_DisabledCommercialProvider):
    name = "ifind"


class ChoiceProvider(_DisabledCommercialProvider):
    name = "choice"
```

- [ ] **Step 4: Verify tests pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_commercial_sources -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add commercial_sources.py tests/test_commercial_sources.py
git commit -m "feat(sources): add commercial provider placeholders"
```

---

### Task 5: Wire Source Attribution Into FundData

**Files:**
- Modify: `monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Add monitor attribution test**

Append to `tests/test_monitor.py`:

```python
    def test_fund_data_defaults_source_attribution(self):
        from monitor import FundData, apply_opportunity_metrics

        fund = FundData(
            code="161129",
            name="原油LOF易方达",
            market_price=1.04,
            nav=1.00,
            nav_date="2026-05-05",
            premium_rate=4.0,
            change_pct=0.1,
            volume=100000,
            turnover_amount=8_000_000,
            sgzt="开放申购",
            shzt="开放赎回",
        )

        [enriched] = apply_opportunity_metrics([fund])

        self.assertEqual(enriched.quote_source, "tencent")
        self.assertIn(enriched.reference_source, {"nav", "iopv"})
        self.assertEqual(enriched.source_warning_count, 0)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_monitor.MonitorIntegrationTests.test_fund_data_defaults_source_attribution -v
```

Expected: failure with `AttributeError` or unexpected missing `quote_source`.

- [ ] **Step 3: Add fields to FundData**

Modify `monitor.py` `FundData`:

```python
    quote_source: str = "tencent"
    nav_source: str = "tencent"
    reference_source_detail: Optional[str] = None
    source_warning_count: int = 0
    source_warnings: tuple[str, ...] = ()
```

In `apply_opportunity_metrics`, after `fund.reference_source = reference.source`, add:

```python
        if fund.reference_source == "iopv":
            fund.reference_source_detail = fund.iopv_base_source or "iopv"
        elif fund.reference_source == "nav":
            fund.reference_source_detail = fund.nav_source
        else:
            fund.reference_source_detail = "missing"
        fund.source_warning_count = len(fund.source_warnings)
```

- [ ] **Step 4: Verify monitor tests pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_monitor -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat(monitor): expose source attribution"
```

---

### Task 6: Add Config Documentation

**Files:**
- Modify: `funds.json`
- Modify: `README.md`

- [ ] **Step 1: Add source config block**

Add to `funds.json`:

```json
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
```

Preserve valid JSON commas around the inserted block.

- [ ] **Step 2: Document source policy**

Add to `README.md` under configuration:

```markdown
### 数据源策略

Moon 支持按 source policy 管理数据源。`primary` 源优先使用，`fallback` 源在主源缺失时补位，`reference` 源只提供 NAV/IOPV 等参考值，`compare-only` 源只参与比对，`disabled` 源不会调用。

iFinD 和 Choice 在默认配置中为 `disabled`。它们只作为正式授权数据源预留，不使用网页抓取或未公开接口。
```

- [ ] **Step 3: Verify JSON and tests**

Run:

```bash
.venv/bin/python -m json.tool funds.json >/tmp/moon-funds-json-check
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: JSON command exits 0; tests pass.

- [ ] **Step 4: Commit**

```bash
git add funds.json README.md
git commit -m "docs(sources): document source policy"
```

---

### Task 7: Full Verification

**Files:**
- All changed files

- [ ] **Step 1: Run unit tests**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 2: Run compile check**

Run:

```bash
.venv/bin/python -m py_compile monitor.py providers.py arbitrage.py estimates.py notifier.py cli.py streamlit_app.py web.py source_models.py source_policy.py source_registry.py commercial_sources.py
```

Expected: exit code 0.

- [ ] **Step 3: Optional live smoke test**

Run only when network access is available:

```bash
.venv/bin/python cli.py 164701 161116 161129 --estimate
```

Expected: CLI prints fund rows or a safe source error without traceback.

- [ ] **Step 4: Commit final verification notes if docs changed**

If verification evidence was added to docs:

```bash
git add docs/superpowers/specs/2026-06-26-multi-source-premium-monitor-design.md docs/superpowers/plans/2026-06-26-multi-source-premium-monitor.md
git commit -m "docs(sources): add multi-source monitor plan"
```

