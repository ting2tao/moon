"""Source registry: provider registration, fallback, and conflict detection."""

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
