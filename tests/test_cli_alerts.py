import unittest


class CliAlertTests(unittest.TestCase):
    def test_filters_alert_rows_with_persistent_cooldown(self):
        from cli import filter_rows_by_cooldown
        from notifier import AlertCooldown

        rows = [
            {"code": "161129", "status": "actionable", "opportunity_direction": "premium"},
            {"code": "164701", "status": "subscription_blocked", "opportunity_direction": "premium"},
        ]
        cooldown = AlertCooldown(cooldown_seconds=600)

        first = filter_rows_by_cooldown(rows, cooldown, now=1000)
        second = filter_rows_by_cooldown(rows, cooldown, now=1200)
        third = filter_rows_by_cooldown(rows, cooldown, now=1701)

        self.assertEqual([r["code"] for r in first], ["161129", "164701"])
        self.assertEqual(second, [])
        self.assertEqual([r["code"] for r in third], ["161129", "164701"])

    def test_alert_rows_do_not_recommend_negative_premium_rows(self):
        from cli import alert_rows
        from monitor import FundData

        fund = FundData(
            code="161129",
            name="原油LOF易方达",
            market_price=0.96,
            nav=1.0,
            nav_date="2026-05-05",
            premium_rate=-4.0,
            change_pct=-0.1,
            volume=100000,
            net_opportunity_rate=2.0,
            opportunity_direction="discount",
            status="redemption_blocked",
        )

        self.assertEqual(alert_rows([fund], {"alert_premium": 3, "net_alert_premium": 0.5}), [])


if __name__ == "__main__":
    unittest.main()
