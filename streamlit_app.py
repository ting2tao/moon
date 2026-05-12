"""Streamlit dashboard for LOF-first on-exchange fund arbitrage monitoring."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from cli import alert_rows, load_config
from monitor import FundData, enrich_with_iopv, fetch_fund_data
from notifier import AlertCooldown, WeChatNotifier, format_alert_markdown


@st.cache_data(ttl=15, show_spinner=False)
def load_dashboard_funds(codes: tuple[str, ...], estimate: bool) -> list[FundData]:
    funds = fetch_fund_data(list(codes))
    if estimate:
        funds = enrich_with_iopv(funds)
    return funds


def fund_to_row(fund: FundData) -> dict:
    return {
        "类型": fund.product_type,
        "代码": fund.code,
        "名称": fund.name,
        "场内价": fund.market_price,
        "参考值": fund.reference_value,
        "默认溢价%": fund.premium_rate,
        "官方溢价%": fund.official_nav_premium_rate,
        "IOPV溢价%": fund.estimated_iopv_premium_rate,
        "精度": fund.iopv_precision,
        "IOPV基准": fund.iopv_base_source,
        "外盘因子": fund.foreign_factor,
        "汇率因子": fund.fx_factor,
        "汇率来源": fund.fx_source,
        "净空间%": fund.net_opportunity_rate,
        "方向": fund.opportunity_direction,
        "成交额万": None if fund.turnover_amount is None else fund.turnover_amount / 10_000,
        "净值日期": fund.nav_date,
        "申购": fund.sgzt,
        "创建": fund.creation_status,
        "赎回": fund.shzt,
        "状态": fund.status,
        "质量": fund.data_quality,
        "错误": fund.error,
    }


def load_codes_from_text(text: str) -> list[str]:
    normalized = text.replace(",", " ").replace("，", " ")
    return [part.strip() for part in normalized.split() if part.strip()]


def main() -> None:
    st.set_page_config(page_title="场内基金折溢价监控", layout="wide")
    config = load_config()

    st.title("场内基金折溢价套利监控")

    with st.sidebar:
        st.header("监控设置")
        codes_text = st.text_area("基金代码", value=" ".join(config.get("codes", [])), height=120)
        estimate = st.checkbox("启用 IOPV", value=bool(config.get("estimate", True)))
        refresh_seconds = st.slider("建议刷新间隔(秒)", min_value=5, max_value=120, value=int(config.get("refresh_seconds", 30)))
        gross_threshold = st.number_input("毛折溢价阈值(%)", value=float(config.get("gross_threshold", 1.5)), step=0.1)
        net_threshold = st.number_input("净空间阈值(%)", value=float(config.get("net_alert_premium", 0.5)), step=0.1)
        min_turnover = st.number_input("最小成交额(万)", value=float(config.get("min_turnover_wan", 500)), step=100.0)
        selected_types = st.multiselect("产品类型", ["LOF", "ETF"], default=config.get("default_product_types", ["LOF"]))
        only_actionable = st.checkbox("只看可行动机会", value=False)
        show_blocked = st.checkbox("保留受限机会", value=True)
        manual_refresh = st.button("立即刷新")
        notify = st.checkbox("触发后发送企业微信", value=False)

    if manual_refresh:
        st.cache_data.clear()

    now = datetime.now()
    st.caption(
        f"刷新时间: {now.strftime('%Y-%m-%d %H:%M:%S')} | "
        f"建议交易时段 {refresh_seconds} 秒刷新；行情请求缓存约 15 秒，可点“立即刷新”清缓存"
    )

    codes = load_codes_from_text(codes_text)
    if not codes:
        st.warning("请输入至少一个基金代码。")
        return

    funds = load_dashboard_funds(tuple(codes), estimate)

    rows = [fund_to_row(f) for f in funds if f.product_type in selected_types]
    df = pd.DataFrame(rows)
    if df.empty:
        st.warning("没有匹配当前筛选条件的基金。")
        return

    if "默认溢价%" in df.columns:
        df = df[df["默认溢价%"].abs().fillna(0) >= gross_threshold]
    if "净空间%" in df.columns:
        df = df[df["净空间%"].fillna(-999) >= net_threshold]
    if "成交额万" in df.columns:
        df = df[(df["成交额万"].isna()) | (df["成交额万"] >= min_turnover)]
    if only_actionable and "状态" in df.columns:
        df = df[df["状态"] == "actionable"]
    elif not show_blocked and "状态" in df.columns:
        df = df[~df["状态"].isin(["subscription_blocked", "redemption_blocked", "creation_blocked"])]

    if "净空间%" in df.columns:
        df = df.sort_values("净空间%", ascending=False, na_position="last")

    def style_status(row):
        status = row.get("状态")
        if status == "actionable":
            return ["background-color: #d7f7df"] * len(row)
        if status in {"subscription_blocked", "redemption_blocked", "creation_blocked"}:
            return ["background-color: #fff1c7"] * len(row)
        if status == "illiquid":
            return ["background-color: #dbeafe"] * len(row)
        if status == "source_error":
            return ["background-color: #ffd6d6"] * len(row)
        return [""] * len(row)

    def style_precision(val):
        if val == "A":
            return "color: #16a34a; font-weight: bold"
        if val == "B":
            return "color: #ca8a04"
        if val == "C":
            return "color: #dc2626"
        if val == "D":
            return "color: #9ca3af"
        return ""

    actionable_count = int((df["状态"] == "actionable").sum()) if "状态" in df.columns else 0
    blocked_count = int(df["状态"].isin(["subscription_blocked", "redemption_blocked", "creation_blocked"]).sum()) if "状态" in df.columns else 0
    top_net = df["净空间%"].max() if "净空间%" in df.columns and not df.empty else None
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("筛选后标的", len(df))
    col2.metric("可行动", actionable_count)
    col3.metric("受限", blocked_count)
    col4.metric("最高净空间", "-" if top_net is None else f"{top_net:.2f}%")

    styled = df.style.apply(style_status, axis=1)
    if "精度" in df.columns:
        styled = styled.map(style_precision, subset=["精度"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    if notify:
        rows_to_send = alert_rows(funds, config)
        if rows_to_send:
            ok, message = WeChatNotifier(cooldown=AlertCooldown()).send_markdown(format_alert_markdown(rows_to_send))
            if ok:
                st.success("企业微信通知已发送。")
            else:
                st.warning(f"企业微信通知未发送: {message}")
        else:
            st.caption("当前无企业微信触发项。")

    st.caption("本页不会自动下单；净空间只用于筛选，实盘前需核对申赎状态、限额、费用和到账时间。")


if __name__ == "__main__":
    main()
