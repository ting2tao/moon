"""Multi-source data models for normalized provider output."""

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
