"""External data provider helpers and source-specific normalization."""

from __future__ import annotations

from typing import Any, Optional


def normalize_code(code: str) -> tuple[str, str]:
    raw = code.strip()
    lower = raw.lower()
    if lower.startswith(("sz", "sh")) and len(lower) >= 8:
        return lower[:2], lower[2:]
    return infer_market_prefix(raw), raw


def infer_market_prefix(code: str) -> str:
    code = code.strip().lower()
    if code.startswith(("sz", "sh")):
        return code[:2]
    if code.startswith(("16", "15")):
        return "sz"
    if code.startswith("5"):
        return "sh"
    return "sz"


def parse_percent(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if text in ("", "-", "--", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "--", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_present(mapping: dict, keys: list[str]):
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def normalize_jisilu_lof_row(row: dict) -> dict:
    cell = row.get("cell") if isinstance(row.get("cell"), dict) else row
    code = str(_first_present(cell, ["fund_id", "id", "code"]) or row.get("id") or "").strip()
    price = parse_float(_first_present(cell, ["price", "last_price", "current_price"]))
    premium = parse_percent(_first_present(cell, ["discount_rt", "premium_rt", "premium_rate"]))
    amount_wan = parse_float(_first_present(cell, ["amount", "volume", "turnover", "turnover_wan"]))

    return {
        "code": code,
        "name": str(_first_present(cell, ["fund_nm", "fund_name", "name"]) or ""),
        "product_type": "LOF",
        "market_price": price,
        "premium_rate": premium,
        "turnover_amount": amount_wan * 10_000 if amount_wan is not None else None,
        "subscription_status": _first_present(cell, ["apply_status", "subscription_status", "sgzt"]),
        "redemption_status": _first_present(cell, ["redeem_status", "redemption_status", "shzt"]),
        "creation_status": None,
    }
