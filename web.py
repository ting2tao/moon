"""Legacy Flask API for the on-exchange fund arbitrage monitor.

The primary dashboard is now `streamlit_app.py`. This module is kept for
backward-compatible JSON API usage and the older HTML template.
"""

from __future__ import annotations

import json
import os

from flask import Flask, jsonify, redirect, render_template, request

from arbitrage import OpportunityConfig
from cli import alert_rows
from monitor import FundData, enrich_with_iopv, fetch_fund_data
from notifier import AlertCooldown, WeChatNotifier, format_alert_markdown

app = Flask(__name__)
ALERT_COOLDOWN = AlertCooldown()

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


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def fund_to_dict(fund: FundData) -> dict:
    return {
        "code": fund.code,
        "name": fund.name,
        "product_type": fund.product_type,
        "market_price": fund.market_price,
        "nav": fund.nav,
        "nav_date": fund.nav_date,
        "reference_value": fund.reference_value,
        "reference_source": fund.reference_source,
        "premium_rate": round(fund.premium_rate, 2) if fund.premium_rate is not None else None,
        "official_nav_premium_rate": round(fund.official_nav_premium_rate, 2)
        if fund.official_nav_premium_rate is not None
        else None,
        "estimated_iopv": round(fund.estimated_iopv, 4) if fund.estimated_iopv is not None else None,
        "iopv_base_source": fund.iopv_base_source,
        "foreign_factor": fund.foreign_factor,
        "fx_factor": fund.fx_factor,
        "estimated_iopv_premium_rate": round(fund.estimated_iopv_premium_rate, 2)
        if fund.estimated_iopv_premium_rate is not None
        else None,
        "iopv_premium": round(fund.iopv_premium, 2) if fund.iopv_premium is not None else None,
        "net_opportunity_rate": round(fund.net_opportunity_rate, 2)
        if fund.net_opportunity_rate is not None
        else None,
        "opportunity_direction": fund.opportunity_direction,
        "turnover_amount": fund.turnover_amount,
        "change_pct": round(fund.change_pct, 2) if fund.change_pct is not None else None,
        "volume": fund.volume,
        "nav_age_days": fund.nav_age_days,
        "subscription_status": fund.sgzt,
        "redemption_status": fund.shzt,
        "creation_status": fund.creation_status,
        "sgzt": fund.sgzt,
        "shzt": fund.shzt,
        "sg_limit": fund.sg_limit,
        "status": fund.status,
        "data_quality": fund.data_quality,
        "error": fund.error,
    }


def load_funds_from_request() -> tuple[list[str], bool]:
    codes_param = request.args.get("codes")
    estimate = request.args.get("estimate", "true").lower() == "true"

    if codes_param:
        codes = [c.strip() for c in codes_param.replace("，", ",").split(",") if c.strip()]
    else:
        codes = load_config().get("codes", [])
    return codes, estimate


@app.route("/")
def index():
    config = load_config()
    if request.args.get("streamlit") == "1":
        return redirect("http://127.0.0.1:8501")
    return render_template(
        "dashboard.html",
        default_funds=",".join(config.get("codes", [])),
        default_estimate="true" if config.get("estimate", True) else "false",
        default_alert=config.get("alert_premium", 5),
        default_refresh=config.get("refresh_seconds", 30),
    )


@app.route("/api/funds")
def api_funds():
    codes, estimate = load_funds_from_request()
    if not codes:
        return jsonify({"error": "未提供基金代码"}), 400

    opportunity_config = OpportunityConfig.from_mapping(load_config())
    funds = fetch_fund_data(codes, opportunity_config)
    if estimate:
        funds = enrich_with_iopv(funds, opportunity_config)

    result = [fund_to_dict(fund) for fund in funds]
    result.sort(
        key=lambda row: row["net_opportunity_rate"]
        if row["net_opportunity_rate"] is not None
        else row["premium_rate"]
        if row["premium_rate"] is not None
        else float("-inf"),
        reverse=True,
    )
    return jsonify(result)


@app.route("/api/alerts")
def api_alerts():
    codes, estimate = load_funds_from_request()
    if not codes:
        return jsonify({"error": "未提供基金代码"}), 400

    config = load_config()
    opportunity_config = OpportunityConfig.from_mapping(config)
    funds = fetch_fund_data(codes, opportunity_config)
    if estimate:
        funds = enrich_with_iopv(funds, opportunity_config)
    rows = alert_rows(funds, config)
    return jsonify({"count": len(rows), "rows": rows, "markdown": format_alert_markdown(rows) if rows else ""})


@app.route("/api/notify", methods=["POST"])
def api_notify():
    data = request.get_json(silent=True) or {}
    codes = data.get("codes") or load_config().get("codes", [])
    estimate = bool(data.get("estimate", True))
    config = load_config()

    opportunity_config = OpportunityConfig.from_mapping(config)
    funds = fetch_fund_data(codes, opportunity_config)
    if estimate:
        funds = enrich_with_iopv(funds, opportunity_config)

    raw_rows = alert_rows(funds, config)
    if not raw_rows:
        return jsonify({"ok": True, "sent": False, "message": "无触发机会"})

    rows = []
    row_keys = []
    for row in raw_rows:
        code = str(row.get("code", ""))
        alert_type = f"{row.get('status', 'unknown')}:{row.get('opportunity_direction', 'none')}"
        if ALERT_COOLDOWN.should_send(code, alert_type):
            rows.append(row)
            row_keys.append((code, alert_type))
    if not rows:
        return jsonify({"ok": True, "sent": False, "message": "冷却中，无新增触发机会"})

    ok, message = WeChatNotifier(cooldown=ALERT_COOLDOWN).send_markdown(format_alert_markdown(rows))
    if ok:
        for code, alert_type in row_keys:
            ALERT_COOLDOWN.mark_sent(code, alert_type)
    return jsonify({"ok": ok, "sent": ok, "message": message, "count": len(rows)})


@app.route("/api/config")
def api_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def api_update_config():
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效数据"}), 400

    config = load_config()
    for key in (
        "codes",
        "default_product_types",
        "estimate",
        "alert_premium",
        "estimate_alert_premium",
        "net_alert_premium",
        "gross_threshold",
        "min_turnover_wan",
        "refresh_seconds",
        "wechat_cooldown_minutes",
    ):
        if key not in data:
            continue
        if key in {"codes", "default_product_types"}:
            config[key] = [str(c).strip() for c in data[key] if str(c).strip()]
        elif key == "estimate":
            config[key] = bool(data[key])
        elif key == "refresh_seconds":
            config[key] = int(data[key])
        else:
            config[key] = float(data[key])

    save_config(config)
    return jsonify({"ok": True, "config": config})


@app.route("/api/sources")
def api_sources():
    return jsonify(
        {
            "primary_dashboard": "streamlit_app.py",
            "legacy_flask": "web.py",
            "fund_quote": {
                "name": "腾讯财经 (qt.gtimg.cn)",
                "fields": {"price": 3, "volume": 6, "change_pct": 32, "premium": 77, "nav": 81},
            },
            "iopv": {
                "formula": "IOPV = T-1净值 x (外盘现价/外盘昨收) x (实时汇率/T-1中间价)",
                "foreign": "腾讯外盘 hf_*",
                "fx": "ExchangeRate API + AkShare BOC fallback",
            },
            "alerts": "Enterprise WeChat via WECHAT_WEBHOOK_URL",
        }
    )


@app.route("/api/funds/add", methods=["POST"])
def api_add_fund():
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "基金代码不能为空"}), 400

    config = load_config()
    config.setdefault("codes", [])
    if code not in config["codes"]:
        config["codes"].append(code)
        save_config(config)
    return jsonify({"ok": True, "codes": config["codes"]})


@app.route("/api/funds/remove", methods=["POST"])
def api_remove_fund():
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    config = load_config()
    if code in config.get("codes", []):
        config["codes"].remove(code)
        save_config(config)
    return jsonify({"ok": True, "codes": config.get("codes", [])})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="场内基金折溢价监控 Legacy Flask API")
    parser.add_argument("--port", "-p", type=int, default=8899, help="端口号（默认 8899）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    config = load_config()
    print(f"启动 Legacy Flask API: http://{args.host}:{args.port}")
    print("主看板请使用: streamlit run streamlit_app.py")
    print(f"监控基金: {', '.join(config.get('codes', []))}")
    app.run(host=args.host, port=args.port, debug=args.debug)
