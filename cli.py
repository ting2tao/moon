"""场内基金折溢价套利监控 - CLI 工具"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from arbitrage import OpportunityConfig
from monitor import FundData, enrich_with_iopv, fetch_fund_data
from notifier import AlertCooldown, WeChatNotifier, format_alert_markdown

console = Console()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "funds.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "codes": ["164701", "161116", "161129"],
        "default_product_types": ["LOF"],
        "estimate": True,
        "alert_premium": 5,
        "estimate_alert_premium": 3,
        "net_alert_premium": 0.5,
        "refresh_seconds": 30,
    }


DEFAULT_FUNDS = load_config().get("codes", ["164701", "161116", "161129"])
NOTIFY_COOLDOWN = AlertCooldown()


def premium_style(rate: float | None) -> str:
    if rate is None:
        return "dim"
    if rate >= 10:
        return "bold red"
    if rate >= 5:
        return "red"
    if rate >= 2:
        return "yellow"
    if rate < 0:
        return "green"
    return ""


def precision_style(level: str) -> str:
    return {
        "A": "bold green",
        "B": "yellow",
        "C": "red",
        "D": "dim red",
    }.get(level, "dim")


def status_style(status: str) -> str:
    return {
        "actionable": "bold white on green",
        "watch_only": "dim",
        "subscription_blocked": "yellow",
        "redemption_blocked": "yellow",
        "creation_blocked": "yellow",
        "illiquid": "blue",
        "source_error": "red",
        "estimate_unavailable": "yellow",
    }.get(status, "")


def format_rate(rate: float | None, alert_threshold: float | None = None) -> Text:
    if rate is None:
        return Text("-", style="dim")
    prefix = "+" if rate > 0 else ""
    text = Text(f"{prefix}{rate:.2f}%", style=premium_style(rate))
    if alert_threshold is not None and rate >= alert_threshold:
        text.stylize("bold white on red")
    return text


def format_money_wan(amount: float | None) -> str:
    if amount is None:
        return "-"
    return f"{amount / 10_000:.0f}万"


def format_status_text(value: str | None, open_word: str = "开放") -> Text:
    if not value:
        return Text("-", style="dim")
    if "暂停" in value:
        return Text("暂停", style="red")
    if open_word in value or "允许" in value:
        return Text("开放", style="green")
    if "限" in value:
        return Text(value[:6], style="yellow")
    return Text(value[:6], style="dim")


def build_table(funds: list[FundData], alert_threshold: float | None = None) -> Table:
    table = Table(
        title=f"场内基金折溢价套利监控  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        show_lines=True,
        title_style="bold cyan",
    )

    table.add_column("代码", style="bold", justify="center", width=8)
    table.add_column("类型", justify="center", width=5)
    table.add_column("名称", width=14)
    table.add_column("场内价", justify="right", width=8)
    table.add_column("参考值", justify="right", width=8)
    table.add_column("默认溢价", justify="right", width=10)
    table.add_column("官方溢价", justify="right", width=10)
    table.add_column("IOPV溢价", justify="right", width=10)
    table.add_column("精度", justify="center", width=4)
    table.add_column("基准", justify="center", width=10)
    table.add_column("净空间", justify="right", width=8)
    table.add_column("方向", justify="center", width=7)
    table.add_column("成交额", justify="right", width=8)
    table.add_column("净值日期", justify="center", width=12)
    table.add_column("申购", justify="center", width=8)
    table.add_column("赎回", justify="center", width=8)
    table.add_column("状态", justify="center", width=14)
    table.add_column("质量", justify="center", width=4)

    sorted_funds = sorted(
        funds,
        key=lambda f: (
            f.net_opportunity_rate
            if f.net_opportunity_rate is not None
            else f.premium_rate
            if f.premium_rate is not None
            else float("-inf")
        ),
        reverse=True,
    )

    for fund in sorted_funds:
        if fund.error:
            table.add_row(
                fund.code,
                fund.product_type,
                fund.name or "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                Text("D", style=precision_style("D")),
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                Text("source_error", style="red"),
                "D",
                style="dim",
            )
            continue

        # 优先显示 IOPV 使用的净值日期（估算或官方）
        date_str = fund.nav_source_date or fund.nav_date or "-"
        if fund.nav_age_days and fund.nav_age_days > 2:
            date_str += " !"

        table.add_row(
            fund.code,
            fund.product_type,
            fund.name,
            f"{fund.market_price:.3f}" if fund.market_price is not None else "-",
            f"{fund.reference_value:.4f}" if fund.reference_value is not None else "-",
            format_rate(fund.premium_rate, alert_threshold),
            format_rate(fund.official_nav_premium_rate, alert_threshold),
            format_rate(fund.estimated_iopv_premium_rate, alert_threshold),
            Text(fund.iopv_precision, style=precision_style(fund.iopv_precision)),
            fund.iopv_base_source or "-",
            format_rate(fund.net_opportunity_rate),
            fund.opportunity_direction,
            format_money_wan(fund.turnover_amount),
            date_str,
            format_status_text(fund.sgzt),
            format_status_text(fund.shzt),
            Text(fund.status, style=status_style(fund.status)),
            fund.data_quality,
        )

    return table


def _fund_alert_row(fund: FundData) -> dict:
    return {
        "product_type": fund.product_type,
        "code": fund.code,
        "name": fund.name,
        "market_price": fund.market_price,
        "reference_value": fund.reference_value,
        "premium_rate": fund.premium_rate,
        "official_nav_premium_rate": fund.official_nav_premium_rate,
        "estimated_iopv_premium_rate": fund.estimated_iopv_premium_rate,
        "net_opportunity_rate": fund.net_opportunity_rate,
        "turnover_amount": fund.turnover_amount,
        "subscription_status": fund.sgzt,
        "creation_status": fund.creation_status,
        "redemption_status": fund.shzt,
        "status": fund.status,
        "data_quality": fund.data_quality,
        "opportunity_direction": fund.opportunity_direction,
    }


def alert_rows(funds: list[FundData], config: dict) -> list[dict]:
    net_threshold = float(config.get("net_alert_premium", 0.5))
    gross_threshold = float(config.get("alert_premium", 5))
    rows = []
    for fund in funds:
        if fund.error:
            continue
        if fund.status == "actionable" and (fund.net_opportunity_rate or 0) >= net_threshold:
            rows.append(_fund_alert_row(fund))
        elif abs(fund.premium_rate or 0) >= gross_threshold and fund.status.endswith("_blocked"):
            rows.append(_fund_alert_row(fund))
    return rows


def filter_rows_by_cooldown(
    rows: list[dict],
    cooldown: AlertCooldown,
    *,
    now: float | None = None,
) -> list[dict]:
    filtered = []
    for row in rows:
        code = str(row.get("code", ""))
        alert_type = f"{row.get('status', 'unknown')}:{row.get('opportunity_direction', 'none')}"
        if cooldown.should_send(code, alert_type, now=now):
            filtered.append(row)
            cooldown.mark_sent(code, alert_type, now=now)
    return filtered


def run_once(
    codes: list[str],
    *,
    estimate: bool = False,
    alert_threshold: float | None = None,
    notify: bool = False,
) -> list[FundData]:
    config = load_config()
    opportunity_config = OpportunityConfig.from_mapping(config)
    funds = fetch_fund_data(codes, opportunity_config)
    if estimate:
        funds = enrich_with_iopv(funds, opportunity_config)

    console.print(build_table(funds, alert_threshold=alert_threshold))

    for fund in funds:
        if fund.error:
            console.print(f"  [dim]x {fund.code}: {fund.error}[/dim]")
        elif fund.nav_age_days and fund.nav_age_days > 2:
            console.print(f"  [yellow]! {fund.code} ({fund.name}) 净值延迟 {fund.nav_age_days} 天[/yellow]")

    if estimate:
        console.print("\n  [dim]IOPV = T-1净值 x (外盘现价/外盘昨收) x (实时汇率/T-1中间价)[/dim]")

    if notify:
        rows = filter_rows_by_cooldown(alert_rows(funds, config), NOTIFY_COOLDOWN)
        if rows:
            content = format_alert_markdown(rows)
            ok, message = WeChatNotifier(cooldown=NOTIFY_COOLDOWN).send_markdown(content)
            style = "green" if ok else "yellow"
            console.print(f"  [{style}]企业微信通知: {message}[/{style}]")
        else:
            console.print("  [dim]企业微信通知: 无触发机会[/dim]")

    return funds


def run_watch(
    codes: list[str],
    interval: int,
    *,
    estimate: bool = False,
    alert_threshold: float | None = None,
    notify: bool = False,
) -> None:
    console.print(f"[dim]Watch 模式：每 {interval} 秒刷新，Ctrl+C 退出[/dim]\n")
    while True:
        try:
            console.clear()
            run_once(codes, estimate=estimate, alert_threshold=alert_threshold, notify=notify)
            time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[dim]已退出监控[/dim]")
            break


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(
        description="场内基金折溢价套利监控工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py 164701 161116 161129
  python cli.py 164701 161116 161129 --estimate
  python cli.py 164701 161116 161129 --watch 30
  python cli.py 161116 --alert 5
  python cli.py 161116 --notify
        """,
    )
    parser.add_argument("codes", nargs="*", default=DEFAULT_FUNDS, help="基金代码列表")
    parser.add_argument("--watch", "-w", type=int, nargs="?", const=30, default=None, help="Watch 模式刷新秒数")
    parser.add_argument("--alert", "-a", type=float, default=config.get("alert_premium"), help="溢价高亮阈值")
    parser.add_argument("--estimate", "-e", action="store_true", default=config.get("estimate", True), help="启用 IOPV")
    parser.add_argument("--notify", action="store_true", help="发送企业微信提醒")

    args = parser.parse_args()
    if args.watch is not None:
        run_watch(args.codes, args.watch, estimate=args.estimate, alert_threshold=args.alert, notify=args.notify)
    else:
        run_once(args.codes, estimate=args.estimate, alert_threshold=args.alert, notify=args.notify)


if __name__ == "__main__":
    main()
