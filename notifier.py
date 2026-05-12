"""Enterprise WeChat alert formatting and delivery."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


def _fmt_pct(value) -> str:
    return "-" if value is None else f"{float(value):.2f}%"


def _fmt_price(value, digits: int = 4) -> str:
    return "-" if value is None else f"{float(value):.{digits}f}"


def _fmt_turnover_wan(value) -> str:
    if value is None:
        return "-"
    return f"{float(value) / 10_000:.2f}万"


def format_alert_markdown(
    rows: Iterable[Mapping],
    *,
    timestamp: Optional[str] = None,
) -> str:
    timestamp = timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "### 场内基金折溢价告警",
        f"> 时间: {timestamp}",
        "",
    ]

    for row in rows:
        status_parts = [
            row.get("subscription_status"),
            row.get("creation_status"),
            row.get("redemption_status"),
        ]
        statuses = " / ".join(str(s) for s in status_parts if s) or "-"
        lines.extend(
            [
                f"**{row.get('product_type', '-') } {row.get('code', '-')} {row.get('name', '-')}**",
                f"> 场内价: {_fmt_price(row.get('market_price'), 3)} | 参考值: {_fmt_price(row.get('reference_value'), 4)}",
                f"> 默认溢价: {_fmt_pct(row.get('premium_rate'))} | 官方: {_fmt_pct(row.get('official_nav_premium_rate'))} | IOPV: {_fmt_pct(row.get('estimated_iopv_premium_rate'))}",
                f"> 净空间: {_fmt_pct(row.get('net_opportunity_rate'))} | 成交额: {_fmt_turnover_wan(row.get('turnover_amount'))}",
                f"> 状态: {row.get('status', '-')} | 质量: {row.get('data_quality', '-')} | 申赎/创建: {statuses}",
                "",
            ]
        )
    return "\n".join(lines).strip()


@dataclass
class AlertCooldown:
    cooldown_seconds: int = 600
    _sent_at: dict[tuple[str, str], float] = field(default_factory=dict)

    def should_send(self, code: str, alert_type: str, *, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        key = (code, alert_type)
        last = self._sent_at.get(key)
        return last is None or now - last >= self.cooldown_seconds

    def mark_sent(self, code: str, alert_type: str, *, now: Optional[float] = None) -> None:
        self._sent_at[(code, alert_type)] = time.time() if now is None else now


class WeChatNotifier:
    def __init__(self, webhook_url: Optional[str] = None, cooldown: Optional[AlertCooldown] = None):
        self.webhook_url = webhook_url or os.environ.get("WECHAT_WEBHOOK_URL")
        self.cooldown = cooldown or AlertCooldown()

    def send_markdown(self, content: str) -> tuple[bool, str]:
        if not self.webhook_url:
            return False, "WECHAT_WEBHOOK_URL 未设置"
        try:
            import requests

            resp = requests.post(
                self.webhook_url,
                json={"msgtype": "markdown", "markdown": {"content": content}},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") == 0:
                return True, "ok"
            return False, str(data)
        except Exception as exc:
            return False, str(exc)
