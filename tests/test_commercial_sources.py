import unittest


class CommercialSourceTests(unittest.TestCase):
    def test_ifind_placeholder_is_disabled_without_credentials(self):
        from commercial_sources import IFindProvider

        provider = IFindProvider(enabled=False)

        self.assertEqual(provider.name, "ifind")
        self.assertFalse(provider.capabilities().quotes)
        self.assertEqual(provider.fetch_quotes(["161129"]), [])
        self.assertEqual(provider.last_error, "disabled_or_unconfigured")

    def test_choice_placeholder_is_disabled_without_credentials(self):
        from commercial_sources import ChoiceProvider

        provider = ChoiceProvider(enabled=False)

        self.assertEqual(provider.name, "choice")
        self.assertFalse(provider.capabilities().quotes)
        self.assertEqual(provider.fetch_references(["161129"]), [])
        self.assertEqual(provider.last_error, "disabled_or_unconfigured")


if __name__ == "__main__":
    unittest.main()
