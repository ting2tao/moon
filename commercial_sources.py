"""Disabled placeholders for commercial data sources (iFinD, Choice)."""

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
