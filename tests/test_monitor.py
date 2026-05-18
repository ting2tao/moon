import unittest


class MonitorIntegrationTests(unittest.TestCase):
    def test_parses_tencent_turnover_amount_from_quote_line(self):
        from monitor import _parse_tencent_line

        line = (
            'v_sz161129="51~原油LOF易方达~161129~2.004~1.919~1.995~4889642~2642891~2246751~'
            '2.004~4355~2.003~41783~2.002~9526~2.001~746~2.000~2441~2.005~2607~'
            '2.006~2573~2.007~485~2.008~1186~2.009~2087~~20260518150603~0.085~'
            '4.43~2.010~1.956~2.004/4889642/969775371~4889642~96978~111.31~~~'
            '2.010~1.956~2.81~8.80~8.80~0.00~2.111~1.727~0.95~49913~1.983'
            '~~~~~~96977.5371~0.0000~0~ ~LOF~82.85~2.98~~~~2.613~1.052~'
            '-3.38~-3.42~62.40~439295599~439295599~73.63~68.54~439295599~'
            '9.69~~67.00~0.25~1.8269~CNY~0~~2.014~-1594~";'
        )

        fund = _parse_tencent_line(line)

        self.assertIsNotNone(fund)
        self.assertEqual(fund.turnover_amount, 969_775_371)

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
