import unittest


class ArbitrageMathTests(unittest.TestCase):
    def test_builds_opportunity_config_from_mapping(self):
        from arbitrage import OpportunityConfig

        cfg = OpportunityConfig.from_mapping(
            {
                "gross_threshold": 2.0,
                "net_alert_premium": 0.8,
                "min_turnover_wan": 300,
            }
        )

        self.assertEqual(cfg.gross_threshold, 2.0)
        self.assertEqual(cfg.net_threshold, 0.8)
        self.assertEqual(cfg.min_turnover_wan, 300)
        self.assertEqual(cfg.subscription_fee_rate, OpportunityConfig.subscription_fee_rate)

    def test_calculates_official_premium_from_price_and_nav(self):
        from arbitrage import calculate_official_premium

        self.assertAlmostEqual(calculate_official_premium(1.23, 1.20), 2.5)
        self.assertIsNone(calculate_official_premium(None, 1.20))
        self.assertIsNone(calculate_official_premium(1.23, 0))

    def test_chooses_iopv_as_reference_before_official_nav(self):
        from arbitrage import choose_reference_value

        reference = choose_reference_value(nav=1.20, estimated_iopv=1.26)
        self.assertEqual(reference.value, 1.26)
        self.assertEqual(reference.source, "iopv")

        fallback = choose_reference_value(nav=1.20, estimated_iopv=None)
        self.assertEqual(fallback.value, 1.20)
        self.assertEqual(fallback.source, "nav")

    def test_calculates_fee_adjusted_premium_and_discount_space(self):
        from arbitrage import OpportunityConfig, calculate_net_opportunity

        cfg = OpportunityConfig(
            subscription_fee_rate=0.15,
            redemption_fee_rate=1.50,
            buy_commission_rate=0.025,
            sell_commission_rate=0.025,
            slippage_buffer=0.20,
        )

        premium = calculate_net_opportunity(104.0, 100.0, cfg)
        self.assertEqual(premium.direction, "premium")
        self.assertAlmostEqual(premium.gross_rate, 4.0)
        self.assertAlmostEqual(premium.net_rate, 3.625)

        discount = calculate_net_opportunity(96.0, 100.0, cfg)
        self.assertEqual(discount.direction, "discount")
        self.assertAlmostEqual(discount.gross_rate, -4.0)
        self.assertAlmostEqual(discount.net_rate, 2.275)

    def test_classifies_lof_status_with_liquidity_and_subscription_rules(self):
        from arbitrage import OpportunityConfig, calculate_net_opportunity, classify_status

        cfg = OpportunityConfig(min_turnover_wan=500, net_threshold=0.5)
        metrics = calculate_net_opportunity(104.0, 100.0, cfg)

        self.assertEqual(
            classify_status(
                product_type="LOF",
                metrics=metrics,
                turnover_amount=8_000_000,
                subscription_status="开放申购",
                redemption_status="开放赎回",
                creation_status=None,
                etf_actionable=False,
                config=cfg,
            ),
            "actionable",
        )

        self.assertEqual(
            classify_status(
                product_type="LOF",
                metrics=metrics,
                turnover_amount=8_000_000,
                subscription_status="暂停申购",
                redemption_status="开放赎回",
                creation_status=None,
                etf_actionable=False,
                config=cfg,
            ),
            "subscription_blocked",
        )

        self.assertEqual(
            classify_status(
                product_type="LOF",
                metrics=metrics,
                turnover_amount=1_000_000,
                subscription_status="开放申购",
                redemption_status="开放赎回",
                creation_status=None,
                etf_actionable=False,
                config=cfg,
            ),
            "illiquid",
        )

    def test_classifies_etf_as_watch_only_until_actionable_configured(self):
        from arbitrage import OpportunityConfig, calculate_net_opportunity, classify_status

        cfg = OpportunityConfig(min_turnover_wan=500, net_threshold=0.5)
        metrics = calculate_net_opportunity(104.0, 100.0, cfg)

        self.assertEqual(
            classify_status(
                product_type="ETF",
                metrics=metrics,
                turnover_amount=8_000_000,
                subscription_status=None,
                redemption_status="开放赎回",
                creation_status="允许申购",
                etf_actionable=False,
                config=cfg,
            ),
            "watch_only",
        )

        self.assertEqual(
            classify_status(
                product_type="ETF",
                metrics=metrics,
                turnover_amount=8_000_000,
                subscription_status=None,
                redemption_status="开放赎回",
                creation_status="允许申购",
                etf_actionable=True,
                config=cfg,
            ),
            "actionable",
        )

    def test_scores_data_quality_for_alert_gating(self):
        from arbitrage import score_data_quality

        self.assertEqual(
            score_data_quality(
                status="actionable",
                nav_age_days=1,
                reference_source="iopv",
                turnover_amount=8_000_000,
            ),
            "A",
        )
        self.assertEqual(
            score_data_quality(
                status="watch_only",
                nav_age_days=3,
                reference_source="nav",
                turnover_amount=8_000_000,
            ),
            "B",
        )
        self.assertEqual(
            score_data_quality(
                status="watch_only",
                nav_age_days=None,
                reference_source="missing",
                turnover_amount=None,
            ),
            "C",
        )
        self.assertEqual(
            score_data_quality(
                status="source_error",
                nav_age_days=1,
                reference_source="iopv",
                turnover_amount=8_000_000,
            ),
            "D",
        )


if __name__ == "__main__":
    unittest.main()
