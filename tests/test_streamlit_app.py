import unittest


class StreamlitAppTests(unittest.TestCase):
    def test_get_alert_cooldown_reuses_session_state_object(self):
        import streamlit_app

        session_state = {}

        first = streamlit_app.get_alert_cooldown(session_state)
        second = streamlit_app.get_alert_cooldown(session_state)

        self.assertIs(first, second)
        self.assertIs(session_state["alert_cooldown"], first)

    def test_dashboard_filter_excludes_negative_premium_rows(self):
        import pandas as pd
        import streamlit_app

        df = pd.DataFrame(
            [
                {"代码": "161129", "默认溢价%": 3.0, "净空间%": 2.0, "成交额万": 800, "状态": "actionable"},
                {"代码": "164701", "默认溢价%": -4.0, "净空间%": 2.5, "成交额万": 900, "状态": "watch_only"},
            ]
        )

        filtered = streamlit_app.filter_dashboard_rows(
            df,
            gross_threshold=1.5,
            net_threshold=0.5,
            min_turnover=500,
            only_actionable=False,
            show_blocked=True,
        )

        self.assertEqual(filtered["代码"].tolist(), ["161129"])


if __name__ == "__main__":
    unittest.main()
