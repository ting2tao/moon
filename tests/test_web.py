import unittest
from unittest.mock import patch


class WebNotifyTests(unittest.TestCase):
    def test_notify_endpoint_reuses_cooldown_between_requests(self):
        import web

        web.ALERT_COOLDOWN._sent_at.clear()
        client = web.app.test_client()
        row = {"code": "161129", "status": "actionable", "opportunity_direction": "premium"}

        class FakeNotifier:
            calls = 0

            def __init__(self, cooldown=None):
                self.cooldown = cooldown

            def send_markdown(self, content):
                FakeNotifier.calls += 1
                return True, "ok"

        with patch.object(web, "fetch_all_lof_premiums", return_value=[]), \
            patch.object(web, "enrich_with_iopv", side_effect=lambda funds: funds), \
            patch.object(web, "alert_rows", return_value=[row]), \
            patch.object(web, "format_alert_markdown", return_value="alert"), \
            patch.object(web, "WeChatNotifier", FakeNotifier):
            first = client.post("/api/notify", json={"codes": ["161129"], "estimate": False})
            second = client.post("/api/notify", json={"codes": ["161129"], "estimate": False})

        self.assertEqual(first.get_json()["sent"], True)
        self.assertEqual(second.get_json()["sent"], False)
        self.assertEqual(second.get_json()["message"], "冷却中，无新增触发机会")
        self.assertEqual(FakeNotifier.calls, 1)

    def test_notify_endpoint_does_not_cool_down_failed_send(self):
        import web

        web.ALERT_COOLDOWN._sent_at.clear()
        client = web.app.test_client()
        row = {"code": "161129", "status": "actionable", "opportunity_direction": "premium"}

        class FakeNotifier:
            calls = 0

            def __init__(self, cooldown=None):
                self.cooldown = cooldown

            def send_markdown(self, content):
                FakeNotifier.calls += 1
                if FakeNotifier.calls == 1:
                    return False, "network error"
                return True, "ok"

        with patch.object(web, "fetch_all_lof_premiums", return_value=[]), \
            patch.object(web, "enrich_with_iopv", side_effect=lambda funds: funds), \
            patch.object(web, "alert_rows", return_value=[row]), \
            patch.object(web, "format_alert_markdown", return_value="alert"), \
            patch.object(web, "WeChatNotifier", FakeNotifier):
            first = client.post("/api/notify", json={"codes": ["161129"], "estimate": False})
            second = client.post("/api/notify", json={"codes": ["161129"], "estimate": False})

        self.assertEqual(first.get_json()["sent"], False)
        self.assertEqual(first.get_json()["message"], "network error")
        self.assertEqual(second.get_json()["sent"], True)
        self.assertEqual(FakeNotifier.calls, 2)


if __name__ == "__main__":
    unittest.main()
