import unittest


class NotifierTests(unittest.TestCase):
    def test_formats_enterprise_wechat_markdown_payload(self):
        from notifier import format_alert_markdown

        content = format_alert_markdown(
            [
                {
                    "product_type": "LOF",
                    "code": "161129",
                    "name": "易方达原油",
                    "market_price": 1.234,
                    "reference_value": 1.2000,
                    "premium_rate": 2.83,
                    "official_nav_premium_rate": 1.12,
                    "estimated_iopv_premium_rate": 2.83,
                    "net_opportunity_rate": 2.45,
                    "turnover_amount": 8_500_000,
                    "subscription_status": "开放申购",
                    "creation_status": None,
                    "redemption_status": "开放赎回",
                    "status": "actionable",
                }
            ],
            timestamp="2026-05-06 10:30:00",
        )

        self.assertIn("场内基金折溢价告警", content)
        self.assertIn("161129", content)
        self.assertIn("净空间: 2.45%", content)
        self.assertIn("成交额: 850.00万", content)

    def test_cooldown_suppresses_repeated_alerts(self):
        from notifier import AlertCooldown

        cooldown = AlertCooldown(cooldown_seconds=600)

        self.assertTrue(cooldown.should_send("161129", "premium", now=1000))
        cooldown.mark_sent("161129", "premium", now=1000)
        self.assertFalse(cooldown.should_send("161129", "premium", now=1200))
        self.assertTrue(cooldown.should_send("161129", "premium", now=1701))


if __name__ == "__main__":
    unittest.main()
