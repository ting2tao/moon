"""场内基金折溢价监控 - 核心数据模块"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from arbitrage import (
    OpportunityConfig,
    calculate_net_opportunity,
    calculate_official_premium,
    choose_reference_value,
    classify_status,
    score_data_quality,
)


@dataclass
class FundData:
    code: str
    name: str
    market_price: Optional[float]  # 场内价格
    nav: Optional[float]  # 最新净值
    nav_date: Optional[str]  # 净值日期
    premium_rate: Optional[float]  # 官方溢价率 %
    change_pct: Optional[float]  # 涨跌幅 %
    volume: Optional[int]  # 成交量（手）
    product_type: str = "LOF"
    turnover_amount: Optional[float] = None  # 成交额（元）
    # IOPV 估算字段
    estimated_iopv: Optional[float] = None
    iopv_premium: Optional[float] = None
    iopv_base_source: Optional[str] = None
    foreign_factor: Optional[float] = None
    fx_factor: Optional[float] = None
    estimated_iopv_premium_rate: Optional[float] = None
    official_nav_premium_rate: Optional[float] = None
    calculated_premium_rate: Optional[float] = None
    raw_premium_rate: Optional[float] = None
    reference_value: Optional[float] = None
    reference_source: str = "missing"
    net_opportunity_rate: Optional[float] = None
    opportunity_direction: str = "none"
    status: str = "ok"
    data_quality: str = "C"
    creation_status: Optional[str] = None
    etf_actionable: bool = False
    nav_age_days: Optional[int] = None
    # 申购赎回状态
    sgzt: Optional[str] = None  # 申购状态：开放申购 / 限大额 / 暂停申购
    shzt: Optional[str] = None  # 赎回状态：开放赎回 / 暂停赎回
    sg_limit: Optional[str] = None  # 申购限额描述，如 "500元" / "10万元"
    error: Optional[str] = None
    # IOPV 净值来源日期（估算净值日期 或 官方净值日期）
    nav_source_date: Optional[str] = None
    # IOPV 精度等级
    iopv_precision: str = "D"  # A/B/C/D
    fx_source: Optional[str] = None  # 汇率来源
    # 数据源归因
    quote_source: str = "tencent"
    nav_source: str = "tencent"
    reference_source_detail: Optional[str] = None
    source_warning_count: int = 0
    source_warnings: tuple[str, ...] = ()


def _fetch_subscription_status(codes: list[str]) -> dict[str, tuple[Optional[str], Optional[str], Optional[str]]]:
    """批量获取申购赎回状态

    Returns:
        {code: (sgzt, shzt, sg_limit)}
    """
    import requests

    result = {}
    for code in codes:
        try:
            resp = requests.get(
                f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={code}&deviceid=wap&plat=Wap&product=EFund&version=2.0.0",
                headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"},
                timeout=10,
            )
            data = resp.json().get("Datas", {})
            sgzt = data.get("SGZT") or None
            shzt = data.get("SHZT") or None

            # 提取限额描述
            sg_limit = None
            if sgzt and "上限" in sgzt:
                try:
                    sg_limit = sgzt.split("上限")[1].rstrip(")")
                except IndexError:
                    pass

            result[code] = (sgzt, shzt, sg_limit)
        except Exception:
            result[code] = (None, None, None)
    return result


def fetch_all_lof_premiums(
    min_premium: float = 0.0,
    opportunity_config: OpportunityConfig | None = None,
) -> list[FundData]:
    """全市场 LOF 基金溢价扫描（东方财富 push2 API）

    Args:
        min_premium: 最低溢价率过滤（%），只返回溢价率 >= 此值的基金
        opportunity_config: 套利配置

    Returns:
        按溢价率降序排列的 FundData 列表
    """
    import requests

    url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://fund.eastmoney.com/",
    }

    # 分页获取全部 LOF 基金（API 每页最多返回 100 条）
    all_items = []
    page = 1
    while True:
        params = {
            "pn": page,
            "pz": 100,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "b:MK0404,b:MK0405,b:MK0406,b:MK0407",
            "fields": "f2,f3,f6,f12,f14,f18",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if page == 1:
                return [FundData(
                    code="", name="", market_price=None, nav=None, nav_date=None,
                    premium_rate=None, change_pct=None, volume=None,
                    error=f"全市场扫描失败: {e}",
                )]
            break

        diff = (data.get("data") or {}).get("diff") or []
        if not diff:
            break
        all_items.extend(diff)
        total = (data.get("data") or {}).get("total") or 0
        if len(all_items) >= total:
            break
        page += 1

    results = []

    for item in all_items:
        code = str(item.get("f12", ""))
        name = str(item.get("f14", ""))
        market_price = _safe_float_from_api(item.get("f2"))
        nav = _safe_float_from_api(item.get("f18"))
        change_pct = _safe_float_from_api(item.get("f3"))
        turnover_amount = _safe_float_from_api(item.get("f6"))

        # 计算溢价率：(场内价 / 净值 - 1) * 100
        premium = None
        if market_price and nav and nav > 0:
            premium = (market_price / nav - 1) * 100

        if premium is None or premium < min_premium:
            continue

        fund = FundData(
            code=code,
            name=name,
            market_price=market_price,
            nav=nav,
            nav_date=None,
            premium_rate=premium,
            raw_premium_rate=premium,
            change_pct=change_pct,
            volume=None,
            turnover_amount=turnover_amount,
            quote_source="eastmoney",
        )
        results.append(fund)

    # 按溢价率降序排列
    results.sort(key=lambda f: f.premium_rate or 0, reverse=True)

    # 获取申购赎回状态（批量，但限制数量避免请求过多）
    codes = [f.code for f in results[:50]]
    if codes:
        sub_status = _fetch_subscription_status(codes)
        for f in results:
            if f.code in sub_status:
                f.sgzt, f.shzt, f.sg_limit = sub_status[f.code]

    return apply_opportunity_metrics(results, opportunity_config)


def _safe_float_from_api(value) -> Optional[float]:
    """从 API 返回值安全解析浮点数"""
    if value is None or value == "-":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def apply_opportunity_metrics(
    funds: list[FundData],
    config: OpportunityConfig | None = None,
) -> list[FundData]:
    """Populate premium, reference, net opportunity, and actionability fields."""
    config = config or OpportunityConfig()

    for fund in funds:
        if fund.error:
            fund.status = "source_error"
            fund.data_quality = "D"
            continue

        fund.calculated_premium_rate = calculate_official_premium(fund.market_price, fund.nav)
        fund.official_nav_premium_rate = (
            fund.calculated_premium_rate
            if fund.calculated_premium_rate is not None
            else fund.raw_premium_rate
            if fund.raw_premium_rate is not None
            else fund.premium_rate
        )

        if fund.estimated_iopv_premium_rate is None and fund.iopv_premium is not None:
            fund.estimated_iopv_premium_rate = fund.iopv_premium

        reference = choose_reference_value(fund.nav, fund.estimated_iopv)
        fund.reference_value = reference.value
        fund.reference_source = reference.source

        # 数据源归因
        if fund.reference_source == "iopv":
            fund.reference_source_detail = fund.iopv_base_source or "iopv"
        elif fund.reference_source == "nav":
            fund.reference_source_detail = fund.nav_source
        else:
            fund.reference_source_detail = "missing"
        fund.source_warning_count = len(fund.source_warnings)

        metrics = calculate_net_opportunity(fund.market_price, fund.reference_value, config)
        fund.opportunity_direction = metrics.direction
        fund.net_opportunity_rate = metrics.net_rate

        if reference.source == "iopv":
            fund.premium_rate = metrics.gross_rate
            fund.estimated_iopv_premium_rate = metrics.gross_rate
            fund.iopv_premium = metrics.gross_rate
        elif fund.official_nav_premium_rate is not None:
            fund.premium_rate = fund.official_nav_premium_rate
        else:
            fund.premium_rate = metrics.gross_rate

        fund.status = classify_status(
            product_type=fund.product_type,
            metrics=metrics,
            turnover_amount=fund.turnover_amount,
            subscription_status=fund.sgzt,
            redemption_status=fund.shzt,
            creation_status=fund.creation_status,
            etf_actionable=fund.etf_actionable,
            config=config,
        )
        fund.data_quality = score_data_quality(
            status=fund.status,
            nav_age_days=fund.nav_age_days,
            reference_source=fund.reference_source,
            turnover_amount=fund.turnover_amount,
        )

    return funds


def enrich_with_iopv(
    funds: list[FundData],
    opportunity_config: OpportunityConfig | None = None,
) -> list[FundData]:
    """为基金列表添加 IOPV 估算数据"""
    from estimates import estimate_all, get_or_detect_config, fetch_estimated_nav

    # 筛选出有配置（或可自动推断）且有数据的基金
    configs = {}
    nav_data = {}
    market_prices = {}

    for f in funds:
        if f.error:
            continue
        cfg = get_or_detect_config(f.code, f.name)
        if not cfg:
            continue
        if f.nav and f.nav > 0:
            configs[f.code] = cfg
            nav_data[f.code] = f.nav
        if f.market_price and f.market_price > 0:
            market_prices[f.code] = f.market_price

    if not configs:
        return funds

    # 收集官方净值日期
    nav_dates = {}
    for f in funds:
        if f.code in configs and f.nav_date:
            nav_dates[f.code] = f.nav_date

    # 获取天天基金实时估值净值（比官方净值更及时，减少 QDII T-2 延迟）
    estimated_navs = fetch_estimated_nav(list(configs.keys()))

    # 批量估算
    results = estimate_all(configs, nav_data, market_prices, estimated_navs, nav_dates)

    # 回填结果
    for f in funds:
        r = results.get(f.code)
        if r and not r.error:
            f.estimated_iopv = r.iopv
            f.iopv_premium = r.iopv_premium
            f.iopv_base_source = r.base_source
            f.foreign_factor = r.foreign_factor
            f.fx_factor = r.fx_factor
            f.estimated_iopv_premium_rate = r.iopv_premium
            f.iopv_precision = r.precision
            f.fx_source = r.fx_source
            if r.nav_source_date:
                f.nav_source_date = r.nav_source_date

    return apply_opportunity_metrics(funds, opportunity_config)


def fetch_nav_history(code: str, page_size: int = 5) -> list[dict]:
    """获取基金历史净值（天天基金 API，备用）"""
    import requests

    url = "https://api.fund.eastmoney.com/f10/lsjz"
    params = {"fundCode": code, "pageIndex": 1, "pageSize": page_size}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://fund.eastmoney.com/",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        if data.get("Data") and data["Data"].get("LSJZList"):
            return [
                {
                    "date": item["FSRQ"],
                    "nav": float(item["DWJZ"]),
                    "acc_nav": float(item["LJJZ"]),
                    "change_pct": item.get("JZZZL"),
                }
                for item in data["Data"]["LSJZList"]
            ]
    except Exception:
        pass
    return []
