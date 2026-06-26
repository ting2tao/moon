"""Source policy: mode handling, fallback thresholds, and config parsing."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SOURCE_MODES = {
    "tencent": "primary",
    "eastmoney": "fallback",
    "tiantian": "reference",
    "ifind": "disabled",
    "choice": "disabled",
}

ALLOWED_MODES = {"primary", "fallback", "reference", "compare-only", "disabled"}


@dataclass(frozen=True)
class SourcePolicy:
    source_modes: dict[str, str]
    compare_enabled: bool = True
    max_price_deviation_pct: float = 0.3
    max_reference_deviation_pct: float = 0.5

    @classmethod
    def from_mapping(cls, values: dict | None) -> "SourcePolicy":
        values = values or {}
        configured_sources = values.get("sources") or {}
        modes = dict(DEFAULT_SOURCE_MODES)
        for source, config in configured_sources.items():
            mode = (config or {}).get("mode", modes.get(source, "disabled"))
            if mode not in ALLOWED_MODES:
                raise ValueError(f"unsupported source mode for {source}: {mode}")
            modes[source] = mode

        compare = values.get("source_compare") or {}
        return cls(
            source_modes=modes,
            compare_enabled=bool(compare.get("enabled", True)),
            max_price_deviation_pct=float(compare.get("max_price_deviation_pct", 0.3)),
            max_reference_deviation_pct=float(compare.get("max_reference_deviation_pct", 0.5)),
        )

    def mode_for(self, source: str) -> str:
        return self.source_modes.get(source, "disabled")

    def enabled_sources(self) -> list[str]:
        return [name for name, mode in self.source_modes.items() if mode != "disabled"]
