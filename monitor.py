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
from providers import infer_market_prefix


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


def _exchange_prefix(code: str) -> str:
    """判断沪深市场前缀：16/15开头→sz(深圳)，5开头→sh(上海)"""
    return infer_market_prefix(code)


def _calc_nav_age(nav_date: Optional[str]) -> Optional[int]:
    """计算净值距今天数"""
    if not nav_date:
        return None
    try:
        dt = datetime.strptime(nav_date, "%Y-%m-%d")
        return (datetime.now() - dt).days
    except ValueError:
        return None


def _parse_tencent_line(line: str) -> Optional[FundData]:
    """解析腾讯财经单行数据"""
    line = line.strip()
    if not line or "=" not in line:
        return None

    start = line.index('"') + 1
    end = line.rindex('"')
    if start >= end:
        return None

    parts = line[start:end].split("~")
    if len(parts) < 82:
        return None

    code = parts[2]
    name = parts[1]

    def safe_float(idx):
        try:
            v = parts[idx].strip()
            return float(v) if v and v != "" else None
        except (ValueError, IndexError):
            return None

    def safe_int(idx):
        try:
            v = parts[idx].strip()
            return int(float(v)) if v and v != "" else None
        except (ValueError, IndexError):
            return None

    market_price = safe_float(3)
    nav = safe_float(81)
    premium_rate = safe_float(77)
    change_pct = safe_float(32) if len(parts) > 32 else None
    volume = safe_int(6)

    # NAV 日期：从字段85附近提取，格式 YYYYMMDD
    nav_date = None
    if len(parts) > 30 and parts[30]:
        raw = parts[30]  # 交易日期时间 如 20260430100945
        if len(raw) >= 8:
            nav_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    return FundData(
        code=code,
        name=name,
        market_price=market_price,
        nav=nav,
        nav_date=nav_date,
        premium_rate=premium_rate,
        raw_premium_rate=premium_rate,
        change_pct=change_pct,
        volume=volume,
        nav_age_days=_calc_nav_age(nav_date),
    )


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


def fetch_fund_data(codes: list[str]) -> list[FundData]:
    """批量获取基金实时数据（腾讯财经 API）"""
    import requests

    if not codes:
        return []

    symbols = [f"{_exchange_prefix(c)}{c}" for c in codes]
    url = f"https://qt.gtimg.cn/q={','.join(symbols)}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://qt.gtimg.cn/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        return [FundData(
            code=c, name="", market_price=None, nav=None, nav_date=None,
            premium_rate=None, change_pct=None, volume=None, error=f"网络错误: {e}"
        ) for c in codes]

    results = []
    found_codes = set()

    for line in resp.text.strip().split("\n"):
        fund = _parse_tencent_line(line)
        if fund:
            found_codes.add(fund.code)
            # 如果 API 没返回溢价率，手动计算
            if fund.premium_rate is None and fund.market_price and fund.nav and fund.nav > 0:
                fund.premium_rate = (fund.market_price - fund.nav) / fund.nav * 100
            fund.calculated_premium_rate = calculate_official_premium(fund.market_price, fund.nav)
            fund.official_nav_premium_rate = fund.premium_rate or fund.calculated_premium_rate
            results.append(fund)

    # 标记未找到的基金
    for c in codes:
        if c not in found_codes:
            results.append(FundData(
                code=c, name="", market_price=None, nav=None, nav_date=None,
                premium_rate=None, change_pct=None, volume=None, error="未找到该基金"
            ))

    # 获取申购赎回状态
    sub_status = _fetch_subscription_status(codes)
    for f in results:
        if f.code in sub_status:
            f.sgzt, f.shzt, f.sg_limit = sub_status[f.code]

    return apply_opportunity_metrics(results)


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
        if fund.official_nav_premium_rate is None:
            fund.official_nav_premium_rate = (
                fund.raw_premium_rate
                if fund.raw_premium_rate is not None
                else fund.premium_rate
                if fund.premium_rate is not None
                else fund.calculated_premium_rate
            )

        if fund.estimated_iopv_premium_rate is None and fund.iopv_premium is not None:
            fund.estimated_iopv_premium_rate = fund.iopv_premium

        reference = choose_reference_value(fund.nav, fund.estimated_iopv)
        fund.reference_value = reference.value
        fund.reference_source = reference.source

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


def enrich_with_iopv(funds: list[FundData]) -> list[FundData]:
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

    return apply_opportunity_metrics(funds)


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
