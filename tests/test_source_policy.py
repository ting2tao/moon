import unittest
from datetime import datetime, timezone


class SourceModelTests(unittest.TestCase):
    def test_source_meta_preserves_attribution_and_quality(self):
        from source_models import SourceMeta

        meta = SourceMeta(
            source="fake",
            source_type="public",
            entitlement="public_best_effort",
            fetched_at=datetime(2026, 6, 26, 9, 30, tzinfo=timezone.utc),
            latency_ms=12,
            freshness_seconds=3,
            quality="A",
            warnings=("fixture",),
        )

        self.assertEqual(meta.source, "fake")
        self.assertEqual(meta.quality, "A")
        self.assertEqual(meta.warnings, ("fixture",))

    def test_quote_and_reference_snapshots_hold_source_meta(self):
        from source_models import SourceMeta, QuoteSnapshot, ReferenceSnapshot

        meta = SourceMeta.fixture("fake")
        quote = QuoteSnapshot(
            symbol="161129",
            market="sz",
            product_type="LOF",
            last_price=1.04,
            bid=None,
            ask=None,
            turnover_amount=8_000_000,
            trade_time=None,
            meta=meta,
        )
        reference = ReferenceSnapshot(
            symbol="161129",
            reference_type="nav",
            value=1.0,
            reference_time=None,
            meta=meta,
        )

        self.assertEqual(quote.meta.source, "fake")
        self.assertEqual(reference.value, 1.0)


class SourcePolicyTests(unittest.TestCase):
    def test_builds_default_policy(self):
        from source_policy import SourcePolicy

        policy = SourcePolicy.from_mapping({})

        self.assertEqual(policy.mode_for("tencent"), "primary")
        self.assertEqual(policy.mode_for("eastmoney"), "fallback")
        self.assertTrue(policy.compare_enabled)

    def test_respects_disabled_and_compare_only_modes(self):
        from source_policy import SourcePolicy

        policy = SourcePolicy.from_mapping(
            {
                "sources": {
                    "ifind": {"mode": "disabled"},
                    "choice": {"mode": "compare-only"},
                },
                "source_compare": {
                    "enabled": True,
                    "max_price_deviation_pct": 0.2,
                    "max_reference_deviation_pct": 0.4,
                },
            }
        )

        self.assertEqual(policy.mode_for("ifind"), "disabled")
        self.assertEqual(policy.mode_for("choice"), "compare-only")
        self.assertEqual(policy.max_price_deviation_pct, 0.2)
        self.assertEqual(policy.max_reference_deviation_pct, 0.4)


if __name__ == "__main__":
    unittest.main()
