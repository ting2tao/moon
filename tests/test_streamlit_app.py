import unittest


class StreamlitAppTests(unittest.TestCase):
    def test_get_alert_cooldown_reuses_session_state_object(self):
        import streamlit_app

        session_state = {}

        first = streamlit_app.get_alert_cooldown(session_state)
        second = streamlit_app.get_alert_cooldown(session_state)

        self.assertIs(first, second)
        self.assertIs(session_state["alert_cooldown"], first)


if __name__ == "__main__":
    unittest.main()
