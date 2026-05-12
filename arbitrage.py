"""Pure calculations for on-exchange fund discount/premium monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OpportunityConfig:
    subscription_fee_rate: float = 0.15
    redemption_fee_rate: float = 1.50
    buy_commission_rate: float = 0.025
    sell_commission_rate: float = 0.025
    slippage_buffer: float = 0.20
    min_turnover_wan: float = 500
    gross_threshold: float = 1.5
    net_threshold: float = 0.5


@dataclass(frozen=True)
class ReferenceValue:
    value: Optional[float]
    source: str


@dataclass(frozen=True)
class ArbitrageMetrics:
    direction: str
    gross_rate: Optional[float]
    net_rate: Optional[float]
    reference_value: Optional[float]
    reference_source: str


def calculate_official_premium(
    market_price: Optional[float],
    nav: Optional[float],
) -> Optional[float]:
    if market_price is None or nav is None or nav <= 0:
        return None
    return (market_price / nav - 1) * 100


def choose_reference_value(
    nav: Optional[float],
    estimated_iopv: Optional[float],
) -> ReferenceValue:
    if estimated_iopv is not None and estimated_iopv > 0:
        return ReferenceValue(estimated_iopv, "iopv")
    if nav is not None and nav > 0:
        return ReferenceValue(nav, "nav")
    return ReferenceValue(None, "missing")


def calculate_net_opportunity(
    market_price: Optional[float],
    reference_value: Optional[float],
    config: OpportunityConfig,
) -> ArbitrageMetrics:
    if market_price is None or reference_value is None or reference_value <= 0:
        return ArbitrageMetrics("none", None, None, reference_value, "missing")

    gross = (market_price / reference_value - 1) * 100
    if gross >= 0:
        net = gross - config.subscription_fee_rate - config.sell_commission_rate - config.slippage_buffer
        direction = "premium"
    else:
        net = abs(gross) - config.buy_commission_rate - config.redemption_fee_rate - config.slippage_buffer
        direction = "discount"

    return ArbitrageMetrics(
        direction=direction,
        gross_rate=round(gross, 6),
        net_rate=round(net, 6),
        reference_value=reference_value,
        reference_source="provided",
    )


def _is_open_status(status: Optional[str]) -> bool:
    if not status:
        return False
    blocked_words = ("暂停", "停止", "关闭", "不可", "禁止")
    if any(word in status for word in blocked_words):
        return False
    open_words = ("开放", "允许", "可", "限")
    return any(word in status for word in open_words)


def classify_status(
    *,
    product_type: str,
    metrics: ArbitrageMetrics,
    turnover_amount: Optional[float],
    subscription_status: Optional[str],
    redemption_status: Optional[str],
    creation_status: Optional[str],
    etf_actionable: bool,
    config: OpportunityConfig,
) -> str:
    if metrics.gross_rate is None or metrics.net_rate is None:
        return "watch_only"

    if abs(metrics.gross_rate) < config.gross_threshold or metrics.net_rate < config.net_threshold:
        return "watch_only"

    min_turnover = config.min_turnover_wan * 10_000
    if turnover_amount is not None and turnover_amount < min_turnover:
        return "illiquid"

    normalized_type = product_type.upper()
    if normalized_type == "ETF":
        if not etf_actionable:
            return "watch_only"
        if metrics.direction == "premium" and not _is_open_status(creation_status):
            return "creation_blocked"
        if metrics.direction == "discount" and not _is_open_status(redemption_status):
            return "redemption_blocked"
        return "actionable"

    if metrics.direction == "premium" and not _is_open_status(subscription_status):
        return "subscription_blocked"
    if metrics.direction == "discount" and not _is_open_status(redemption_status):
        return "redemption_blocked"
    return "actionable"


def score_data_quality(
    *,
    status: str,
    nav_age_days: Optional[int],
    reference_source: str,
    turnover_amount: Optional[float],
) -> str:
    """Return A-D data quality grade for alert gating and UI display."""
    if status == "source_error":
        return "D"
    if reference_source == "missing":
        return "C"
    if turnover_amount is None:
        return "C"
    if nav_age_days is not None and nav_age_days > 2:
        return "B"
    if reference_source == "iopv" and status in {"actionable", "watch_only"}:
        return "A"
    return "B"
