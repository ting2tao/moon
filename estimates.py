"""LOF/QDII 基金 IOPV 实时估算引擎

公式：IOPV ≈ base_nav × (外盘现价 / 外盘昨收) × (实时汇率 / T-1汇率中间价)
溢价率 = (场内实时价 / IOPV - 1) × 100%

base_nav 优先使用天天基金实时估值净值（已包含 T-1 外盘变动），
回退到腾讯 API 的官方净值（QDII 基金可能有 T-2 延迟）。
"""

import requests
from dataclasses import dataclass
from typing import Optional


@dataclass
class FundEstimateConfig:
    code: str
    name: str
    estimate_type: str   # GOLD / OIL / BRENT / SP500
    foreign_proxy: str   # 腾讯外盘代码: hf_GC / hf_CL / hf_OIL / hf_ES
    fx_pair: str = "CNH" # CNH 或 CNY


@dataclass
class EstimateResult:
    iopv: Optional[float] = None
    iopv_premium: Optional[float] = None
    foreign_current: Optional[float] = None
    foreign_prev_close: Optional[float] = None
    fx_current: Optional[float] = None
    fx_base: Optional[float] = None
    base_nav: Optional[float] = None
    base_source: Optional[str] = None  # estimated_nav / official_nav
    nav_source_date: Optional[str] = None  # 净值日期（估算或官方）
    foreign_factor: Optional[float] = None
    fx_factor: Optional[float] = None
    error: Optional[str] = None
    precision: str = "D"  # A/B/C/D 精度等级
    fx_source: Optional[str] = None  # 汇率来源


# 已知基金配置
FUND_CONFIGS: dict[str, FundEstimateConfig] = {
    # 黄金
    "164701": FundEstimateConfig("164701", "黄金LOF", "GOLD", "hf_GC"),
    "161116": FundEstimateConfig("161116", "黄金主题LOF", "GOLD", "hf_GC"),
    "160719": FundEstimateConfig("160719", "嘉实黄金LOF", "GOLD", "hf_GC"),
    "164815": FundEstimateConfig("164815", "工银黄金LOF", "GOLD", "hf_GC"),
    # 白银
    "161226": FundEstimateConfig("161226", "国投白银LOF", "SILVER", "hf_SI"),
    # 原油
    "161129": FundEstimateConfig("161129", "原油LOF易方达", "OIL", "hf_CL"),
    "160723": FundEstimateConfig("160723", "嘉实原油LOF", "OIL", "hf_CL"),
    "162719": FundEstimateConfig("162719", "石油LOF", "OIL", "hf_CL"),
    "160416": FundEstimateConfig("160416", "石油基金LOF", "OIL", "hf_CL"),
    "162411": FundEstimateConfig("162411", "华宝油气LOF", "OIL", "hf_CL"),
    "501018": FundEstimateConfig("501018", "南方原油LOF", "OIL", "hf_CL"),
    "160216": FundEstimateConfig("160216", "国泰商品LOF", "OIL", "hf_CL"),
    "165513": FundEstimateConfig("165513", "中信保诚商品LOF", "OIL", "hf_CL"),
    "161815": FundEstimateConfig("161815", "抗通胀LOF", "OIL", "hf_CL"),
    # 标普500
    "161128": FundEstimateConfig("161128", "标普信息科技LOF", "SP500", "hf_ES"),
    "162415": FundEstimateConfig("162415", "美国消费LOF", "SP500", "hf_ES"),
    # 纳斯达克
    "161125": FundEstimateConfig("161125", "纳斯达克100LOF", "NASDAQ", "hf_ES"),
    "161130": FundEstimateConfig("161130", "纳斯达克100LOF", "NASDAQ", "hf_ES"),
    "160213": FundEstimateConfig("160213", "国泰纳斯达克100LOF", "NASDAQ", "hf_ES"),
    "501312": FundEstimateConfig("501312", "海外科技LOF", "NASDAQ", "hf_ES"),
    "501225": FundEstimateConfig("501225", "全球芯片LOF", "NASDAQ", "hf_ES"),
    # 港美互联网（用港股恒生科技ETF作代理，与A股同步交易）
    "160644": FundEstimateConfig("160644", "港美互联网LOF", "KWEB", "hk03032"),
    # 恒生/港股
    "164705": FundEstimateConfig("164705", "恒生LOF", "HSI", "hf_HSI"),
    "161124": FundEstimateConfig("161124", "港股小盘LOF", "HSI", "hf_HSI"),
    "501301": FundEstimateConfig("501301", "香港大盘LOF", "HSI", "hf_HSI"),
    # 印度（用美股 INDA ETF 作代理）
    "164824": FundEstimateConfig("164824", "印度基金LOF", "INDIA", "usINDA"),
}

# 基金名称关键词 → 代理类型映射（用于自动推断未配置的基金）
_NAME_TYPE_MAP: list[tuple[str, str, str]] = [
    # (关键词, estimate_type, foreign_proxy)
    ("原油", "OIL", "hf_CL"),
    ("石油", "OIL", "hf_CL"),
    ("油气", "OIL", "hf_CL"),
    ("商品", "OIL", "hf_CL"),
    ("抗通胀", "OIL", "hf_CL"),
    ("黄金", "GOLD", "hf_GC"),
    ("白银", "SILVER", "hf_SI"),
    ("标普", "SP500", "hf_ES"),
    ("美国消费", "SP500", "hf_ES"),
    ("纳斯达克", "NASDAQ", "hf_ES"),
    ("纳指", "NASDAQ", "hf_ES"),
    ("海外科技", "NASDAQ", "hf_ES"),
    ("全球芯片", "NASDAQ", "hf_ES"),
    ("恒生", "HSI", "hf_HSI"),
    ("港股", "HSI", "hf_HSI"),
    ("香港", "HSI", "hf_HSI"),
    ("印度", "INDIA", "usINDA"),
    ("港美互联网", "KWEB", "hk03032"),
]

# 缓存：同一刷新周期内复用数据
_foreign_cache: dict[str, tuple[float, float]] = {}  # proxy -> (current, prev_close)
_fx_cache: Optional[tuple[float, float]] = None       # (current_cnh, base_cnh)
_estimated_nav_cache: dict[str, tuple[float, str]] = {}  # code -> (estimated_nav, date_str)
_cache_valid = False


def _invalidate_cache():
    global _foreign_cache, _fx_cache, _estimated_nav_cache, _cache_valid
    _foreign_cache = {}
    _fx_cache = None
    _estimated_nav_cache = {}
    _cache_valid = False


def _grade_precision(
    base_source: Optional[str],
    fx_data: tuple[Optional[float], Optional[float], str],
) -> str:
    """根据数据源质量判定精度等级 A/B/C/D"""
    fx_current, fx_base, fx_source = fx_data

    # D 级：缺少基础数据
    if base_source is None:
        return "D"

    has_real_fx = (
        fx_source == "boc_midrate"
        and fx_current is not None
        and fx_base is not None
        and fx_base > 0
        and abs(fx_current / fx_base - 1.0) > 0.0001
    )

    if base_source == "estimated_nav":
        # 估算净值 + 央行中间价修正 = A；汇率近似 = B
        return "A" if has_real_fx else "B"
    else:
        # 官方净值（可能 T-2）= C
        return "C"


def _parse_tencent_foreign(line: str) -> Optional[tuple[str, float, float]]:
    """解析腾讯外盘/美股/港股数据，返回 (symbol, current_price, prev_close)

    支持两种格式：
    - 外盘期货(逗号分隔): v_hf_GC="4630.45,...,4561.50,..."  [0]=现价 [7]=昨收
    - 股票/ETF(~分隔): v_usINDA / v_hk03032  [3]=现价 [4]=昨收
    """
    line = line.strip()
    if not line or "=" not in line or '=""' in line:
        return None

    # 提取 symbol: v_hf_GC="..." -> hf_GC, v_usINDA="..." -> usINDA, v_hk03032 -> hk03032
    var_part = line.split("=")[0]
    symbol = var_part.split("_", 1)[-1] if "_" in var_part else var_part

    start = line.index('"') + 1
    end = line.rindex('"')
    if start >= end:
        return None

    content = line[start:end]

    # 外盘期货格式（逗号分隔，字段数 ≥ 8）
    if "," in content:
        fields = content.split(",")
        if len(fields) < 8:
            return None
        try:
            current = float(fields[0])
            prev_close = float(fields[7])
            if current <= 0 or prev_close <= 0:
                return None
            return (symbol, current, prev_close)
        except (ValueError, IndexError):
            return None

    # 股票/ETF 格式（~分隔，字段数 ≥ 10）：美股、港股通用
    if "~" in content:
        fields = content.split("~")
        if len(fields) < 10:
            return None
        try:
            current = float(fields[3])
            prev_close = float(fields[4])
            if current <= 0 or prev_close <= 0:
                return None
            return (symbol, current, prev_close)
        except (ValueError, IndexError):
            return None

    return None


def fetch_foreign_quotes(proxies: list[str]) -> dict[str, tuple[float, float]]:
    """批量获取外盘期货现价和昨收

    Args:
        proxies: 腾讯外盘代码列表，如 ["hf_GC", "hf_CL"]

    Returns:
        {symbol: (current_price, prev_close)}
    """
    global _foreign_cache, _cache_valid

    # 检查缓存
    missing = [p for p in proxies if p not in _foreign_cache]
    if not missing:
        return {p: _foreign_cache[p] for p in proxies if p in _foreign_cache}

    url = f"http://qt.gtimg.cn/q={','.join(missing)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return {p: _foreign_cache[p] for p in proxies if p in _foreign_cache}

    for line in resp.text.strip().split("\n"):
        parsed = _parse_tencent_foreign(line)
        if parsed:
            symbol, current, prev_close = parsed
            _foreign_cache[symbol] = (current, prev_close)

    _cache_valid = True
    return {p: _foreign_cache[p] for p in proxies if p in _foreign_cache}


def fetch_fx_rate() -> tuple[Optional[float], Optional[float], str]:
    """获取实时 USD/CNH 汇率和 T-1 央行中间价

    Returns:
        (realtime_cnh, base_cnh, fx_source) 或 (None, None, "failed")
    """
    global _fx_cache

    if _fx_cache is not None:
        return _fx_cache

    # 1. 实时汇率（主源：open.er-api.com）
    realtime_cnh = None
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=10,
        )
        data = resp.json()
        realtime_cnh = data.get("rates", {}).get("CNH")
        if realtime_cnh is None:
            realtime_cnh = data.get("rates", {}).get("CNY")
    except Exception:
        pass

    # 1b. 实时汇率备用源（新浪财经）
    if realtime_cnh is None:
        try:
            import re as _re
            resp = requests.get(
                "https://hq.sinajs.cn/rn=1&list=fx_susdcnh",
                headers={"Referer": "https://finance.sina.com.cn/"},
                timeout=10,
            )
            match = _re.search(r'"([^"]+)"', resp.text)
            if match:
                fields = match.group(1).split(",")
                if len(fields) >= 1:
                    realtime_cnh = float(fields[0])
        except Exception:
            pass

    # 2. T-1 央行中间价（主源：AkShare BOC）
    base_cnh = None
    fx_source = "realtime_only"
    try:
        import akshare as ak
        df = ak.currency_boc_sina(symbol="美元", start_date="20260101", end_date="20261231")
        if not df.empty:
            latest = df.iloc[-1]
            raw_rate = float(latest["央行中间价"])
            base_cnh = raw_rate / 100.0
            fx_source = "boc_midrate"
    except Exception:
        pass

    # 2b. 央行中间价备用源：用前一交易日的近似值（实时汇率 ± 小幅偏差）
    # 如果央行中间价获取失败，用实时汇率作为近似（fx_factor ≈ 1.0，精度降级）
    if base_cnh is None and realtime_cnh is not None:
        base_cnh = realtime_cnh
        fx_source = "realtime_approx"

    if realtime_cnh is None and base_cnh is None:
        fx_source = "failed"

    _fx_cache = (realtime_cnh, base_cnh, fx_source)
    return _fx_cache


def fetch_estimated_nav(codes: list[str]) -> dict[str, tuple[float, str]]:
    """批量获取天天基金实时估值净值（比官方净值更及时）

    QDII 基金的官方净值通常有 T-1 ~ T-2 延迟，而天天基金的估值 API
    基于持仓和实时行情估算净值，可提前 1 天获取更接近真实的净值。

    Returns:
        {code: (estimated_nav, date_str)}，不支持或数据过期的基金不会包含在结果中
    """
    import json as _json
    from datetime import datetime, timedelta

    global _estimated_nav_cache

    missing = [c for c in codes if c not in _estimated_nav_cache]
    if not missing:
        return {c: _estimated_nav_cache[c] for c in codes if c in _estimated_nav_cache}

    cutoff = datetime.now() - timedelta(hours=24)

    for code in missing:
        try:
            resp = requests.get(
                f"https://fundgz.1234567.com.cn/js/{code}.js",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Referer": "https://fund.eastmoney.com/",
                },
                timeout=10,
            )
            text = resp.text
            if "(" not in text:
                continue
            json_str = text[text.index("(") + 1:text.rindex(")")]
            data = _json.loads(json_str)

            gsz = data.get("gsz")
            gztime = data.get("gztime")
            if not gsz or not gztime:
                continue

            # 检查估值是否在 24h 内
            est_time = datetime.strptime(gztime, "%Y-%m-%d %H:%M")
            if est_time < cutoff:
                continue

            # 取日期部分作为显示用（如 "2026-05-08"）
            date_str = gztime.split(" ")[0] if " " in gztime else gztime
            _estimated_nav_cache[code] = (float(gsz), date_str)
        except Exception:
            continue

    return {c: _estimated_nav_cache[c] for c in codes if c in _estimated_nav_cache}


def estimate_iopv(
    config: FundEstimateConfig,
    base_nav: float,
    market_price: float,
    foreign_data: tuple[float, float],
    fx_data: tuple[Optional[float], Optional[float], str],
    *,
    base_source: str = "official_nav",
) -> EstimateResult:
    """计算单只基金的 IOPV

    Args:
        config: 基金估算配置
        base_nav: T-1 官方净值
        market_price: 场内实时价格
        foreign_data: (外盘现价, 外盘昨收)
        fx_data: (实时汇率, T-1汇率中间价, 汇率来源)
    """
    foreign_current, foreign_prev_close = foreign_data
    fx_current, fx_base, fx_source = fx_data

    # 外盘变动因子（无论 base_source 都需要计算）
    if foreign_prev_close <= 0:
        return EstimateResult(
            base_nav=base_nav,
            foreign_current=foreign_current,
            foreign_prev_close=foreign_prev_close,
            base_source=base_source,
            error="外盘昨收价无效",
        )
    foreign_factor = foreign_current / foreign_prev_close

    # 汇率变动因子
    fx_factor = 1.0
    if fx_current and fx_base and fx_base > 0:
        fx_factor = fx_current / fx_base

    # IOPV = base_nav × 外盘变动 × 汇率变动
    # 无论 base_nav 来自天天基金估算还是官方净值，都应用外盘和汇率修正
    iopv = base_nav * foreign_factor * fx_factor

    # IOPV 溢价率
    iopv_premium = None
    if iopv > 0 and market_price:
        iopv_premium = (market_price / iopv - 1) * 100

    # 精度等级判定
    precision = _grade_precision(base_source, fx_data)

    return EstimateResult(
        iopv=round(iopv, 4),
        iopv_premium=round(iopv_premium, 2) if iopv_premium is not None else None,
        foreign_current=foreign_current,
        foreign_prev_close=foreign_prev_close,
        fx_current=fx_current,
        fx_base=fx_base,
        base_nav=base_nav,
        base_source=base_source,
        foreign_factor=round(foreign_factor, 6),
        fx_factor=round(fx_factor, 6),
        precision=precision,
        fx_source=fx_source,
    )


def estimate_all(
    fund_configs: dict[str, FundEstimateConfig],
    nav_data: dict[str, float],
    market_prices: dict[str, float],
    estimated_navs: dict[str, tuple[float, str]] | None = None,
    nav_dates: dict[str, str] | None = None,
) -> dict[str, EstimateResult]:
    """批量估算 IOPV

    Args:
        fund_configs: {code: config}
        nav_data: {code: t-1_nav}  官方净值（可能有 T-2 延迟）
        market_prices: {code: market_price}
        estimated_navs: {code: (estimated_nav, date_str)}  天天基金实时估值（可选）
        nav_dates: {code: date_str}  官方净值日期

    Returns:
        {code: EstimateResult}
    """
    # 收集所有需要的外盘代理
    all_proxies = list(set(c.foreign_proxy for c in fund_configs.values()))

    # 批量获取外盘数据和汇率
    foreign_quotes = fetch_foreign_quotes(all_proxies)
    fx_data = fetch_fx_rate()

    results = {}
    for code, config in fund_configs.items():
        market_price = market_prices.get(code)

        # 优先使用天天基金实时估值净值（已包含 T-1 外盘变动），
        # 回退到官方净值（可能有 T-2 延迟）
        base_nav = None
        source_date = None
        base_source = "official_nav"
        if estimated_navs and code in estimated_navs:
            base_nav, source_date = estimated_navs[code]
            base_source = "estimated_nav"
        if base_nav is None:
            base_nav = nav_data.get(code)
            source_date = (nav_dates or {}).get(code)
            base_source = "official_nav"

        if base_nav is None or base_nav <= 0:
            results[code] = EstimateResult(error="缺少净值数据")
            continue

        if market_price is None or market_price <= 0:
            results[code] = EstimateResult(error="缺少场内价格")
            continue

        proxy_data = foreign_quotes.get(config.foreign_proxy)
        if proxy_data is None:
            results[code] = EstimateResult(
                base_nav=base_nav,
                nav_source_date=source_date,
                error=f"外盘数据获取失败: {config.foreign_proxy}",
            )
            continue

        r = estimate_iopv(config, base_nav, market_price, proxy_data, fx_data, base_source=base_source)
        r.nav_source_date = source_date
        results[code] = r

    return results


def get_config(code: str) -> Optional[FundEstimateConfig]:
    """获取基金估算配置"""
    return FUND_CONFIGS.get(code)


def auto_detect_config(code: str, name: str) -> Optional[FundEstimateConfig]:
    """根据基金名称自动推断估算配置"""
    if not name:
        return None
    for keyword, est_type, proxy in _NAME_TYPE_MAP:
        if keyword in name:
            return FundEstimateConfig(code, name, est_type, proxy)
    return None


def get_or_detect_config(code: str, name: str) -> Optional[FundEstimateConfig]:
    """获取配置，如果没有则尝试自动推断"""
    cfg = FUND_CONFIGS.get(code)
    if cfg:
        return cfg
    return auto_detect_config(code, name)


def register_config(config: FundEstimateConfig):
    """注册自定义基金配置"""
    FUND_CONFIGS[config.code] = config
