import unittest


class EstimateAccuracyTests(unittest.TestCase):
    def test_estimated_nav_is_adjusted_by_foreign_and_fx(self):
        """估算净值也应乘以外盘和汇率因子"""
        import estimates
        from estimates import FundEstimateConfig, estimate_all

        original_foreign = estimates.fetch_foreign_quotes
        original_fx = estimates.fetch_fx_rate
        try:
            estimates.fetch_foreign_quotes = lambda proxies: {"hf_OIL": (110.0, 100.0)}
            estimates.fetch_fx_rate = lambda: (7.7, 7.0, "boc_midrate")

            result = estimate_all(
                {"161129": FundEstimateConfig("161129", "原油LOF易方达", "OIL", "hf_OIL")},
                nav_data={"161129": 1.0},
                market_prices={"161129": 1.2},
                estimated_navs={"161129": (1.1, "2026-05-12")},
                nav_dates={"161129": "2026-05-09"},
            )["161129"]

            # IOPV = 1.1 * (110/100) * (7.7/7.0) = 1.1 * 1.1 * 1.1 = 1.331
            self.assertAlmostEqual(result.iopv, 1.331)
            self.assertAlmostEqual(result.foreign_factor, 1.1)
            self.assertAlmostEqual(result.fx_factor, 1.1)
            self.assertEqual(result.base_source, "estimated_nav")
            self.assertEqual(result.nav_source_date, "2026-05-12")
            self.assertEqual(result.precision, "A")
        finally:
            estimates.fetch_foreign_quotes = original_foreign
            estimates.fetch_fx_rate = original_fx

    def test_official_nav_still_uses_foreign_and_fx_adjustment(self):
        import estimates
        from estimates import FundEstimateConfig, estimate_all

        original_foreign = estimates.fetch_foreign_quotes
        original_fx = estimates.fetch_fx_rate
        try:
            estimates.fetch_foreign_quotes = lambda proxies: {"hf_OIL": (110.0, 100.0)}
            estimates.fetch_fx_rate = lambda: (7.7, 7.0, "boc_midrate")

            result = estimate_all(
                {"161129": FundEstimateConfig("161129", "原油LOF易方达", "OIL", "hf_OIL")},
                nav_data={"161129": 1.0},
                market_prices={"161129": 1.2},
                estimated_navs={},
                nav_dates={"161129": "2026-05-09"},
            )["161129"]

            self.assertAlmostEqual(result.iopv, 1.21)
            self.assertAlmostEqual(result.foreign_factor, 1.1)
            self.assertAlmostEqual(result.fx_factor, 1.1)
            self.assertEqual(result.base_source, "official_nav")
            self.assertEqual(result.precision, "C")
        finally:
            estimates.fetch_foreign_quotes = original_foreign
            estimates.fetch_fx_rate = original_fx

    def test_precision_grading(self):
        """验证精度等级判定"""
        import estimates
        from estimates import FundEstimateConfig, estimate_all

        original_foreign = estimates.fetch_foreign_quotes
        original_fx = estimates.fetch_fx_rate
        try:
            estimates.fetch_foreign_quotes = lambda proxies: {"hf_OIL": (110.0, 100.0)}

            # A 级：估算净值 + 央行中间价
            estimates.fetch_fx_rate = lambda: (7.7, 7.0, "boc_midrate")
            r = estimate_all(
                {"161129": FundEstimateConfig("161129", "原油LOF", "OIL", "hf_OIL")},
                nav_data={"161129": 1.0},
                market_prices={"161129": 1.2},
                estimated_navs={"161129": (1.1, "2026-05-12")},
            )["161129"]
            self.assertEqual(r.precision, "A")

            # B 级：估算净值 + 实时汇率近似
            estimates._fx_cache = None
            estimates.fetch_fx_rate = lambda: (7.7, 7.7, "realtime_approx")
            r = estimate_all(
                {"161129": FundEstimateConfig("161129", "原油LOF", "OIL", "hf_OIL")},
                nav_data={"161129": 1.0},
                market_prices={"161129": 1.2},
                estimated_navs={"161129": (1.1, "2026-05-12")},
            )["161129"]
            self.assertEqual(r.precision, "B")

            # C 级：官方净值
            estimates._fx_cache = None
            estimates.fetch_fx_rate = lambda: (7.7, 7.0, "boc_midrate")
            r = estimate_all(
                {"161129": FundEstimateConfig("161129", "原油LOF", "OIL", "hf_OIL")},
                nav_data={"161129": 1.0},
                market_prices={"161129": 1.2},
                estimated_navs={},
            )["161129"]
            self.assertEqual(r.precision, "C")
        finally:
            estimates.fetch_foreign_quotes = original_foreign
            estimates.fetch_fx_rate = original_fx
            estimates._fx_cache = None


if __name__ == "__main__":
    unittest.main()
