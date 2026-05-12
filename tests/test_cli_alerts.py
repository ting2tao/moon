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


if __name__ == "__main__":
    unittest.main()
