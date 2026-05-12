import unittest


class MonitorIntegrationTests(unittest.TestCase):
    def test_applies_iopv_reference_and_actionable_status_to_fund(self):
        from monitor import FundData, apply_opportunity_metrics
        from arbitrage import OpportunityConfig

        fund = FundData(
            code="161129",
            name="原油LOF易方达",
            market_price=1.04,
            nav=1.00,
            nav_date="2026-05-05",
            premium_rate=4.0,
            change_pct=0.1,
            volume=100000,
            estimated_iopv=1.02,
            turnover_amount=8_000_000,
            sgzt="开放申购",
            shzt="开放赎回",
        )

        [enriched] = apply_opportunity_metrics(
            [fund],
            OpportunityConfig(min_turnover_wan=500, net_threshold=0.5),
        )

        self.assertEqual(enriched.product_type, "LOF")
        self.assertAlmostEqual(enriched.official_nav_premium_rate, 4.0)
        self.assertAlmostEqual(enriched.premium_rate, 1.960784, places=5)
        self.assertAlmostEqual(enriched.reference_value, 1.02)
        self.assertEqual(enriched.reference_source, "iopv")
        self.assertEqual(enriched.status, "actionable")
        self.assertEqual(enriched.data_quality, "A")
        self.assertGreater(enriched.net_opportunity_rate, 1.0)
        self.assertIsNone(enriched.iopv_base_source)

    def test_marks_error_rows_as_source_error_quality_d(self):
        from monitor import FundData, apply_opportunity_metrics

        fund = FundData(
            code="000000",
            name="",
            market_price=None,
            nav=None,
            nav_date=None,
            premium_rate=None,
            change_pct=None,
            volume=None,
            error="网络错误",
        )

        [enriched] = apply_opportunity_metrics([fund])

        self.assertEqual(enriched.status, "source_error")
        self.assertEqual(enriched.data_quality, "D")


if __name__ == "__main__":
    unittest.main()
