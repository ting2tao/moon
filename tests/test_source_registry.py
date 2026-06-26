import unittest


class FakeQuoteProvider:
    def __init__(self, name, price, mode_quality="A"):
        from source_models import SourceCapabilities

        self.name = name
        self.price = price
        self._capabilities = SourceCapabilities(quotes=True, markets=("cn",), product_types=("LOF",))
        self.mode_quality = mode_quality

    def capabilities(self):
        return self._capabilities

    def fetch_quotes(self, symbols):
        from source_models import QuoteSnapshot, SourceMeta

        if self.price is None:
            return []
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                market="sz",
                product_type="LOF",
                last_price=self.price,
                bid=None,
                ask=None,
                turnover_amount=8_000_000,
                trade_time=None,
                meta=SourceMeta.fixture(self.name, self.mode_quality),
            )
        ]

    def fetch_references(self, symbols):
        return []

    def fetch_statuses(self, symbols):
        return []


class SourceRegistryTests(unittest.TestCase):
    def test_falls_back_when_primary_has_no_quote(self):
        from source_policy import SourcePolicy
        from source_registry import SourceRegistry

        registry = SourceRegistry(
            [FakeQuoteProvider("primary", None), FakeQuoteProvider("fallback", 1.23)],
            SourcePolicy.from_mapping(
                {
                    "sources": {
                        "primary": {"mode": "primary"},
                        "fallback": {"mode": "fallback"},
                    }
                }
            ),
        )

        result = registry.fetch_best_quotes(["161129"])

        self.assertEqual(result["161129"].last_price, 1.23)
        self.assertEqual(result["161129"].meta.source, "fallback")

    def test_marks_conflict_when_compare_source_deviates(self):
        from source_policy import SourcePolicy
        from source_registry import SourceRegistry

        registry = SourceRegistry(
            [FakeQuoteProvider("primary", 1.00), FakeQuoteProvider("compare", 1.02)],
            SourcePolicy.from_mapping(
                {
                    "sources": {
                        "primary": {"mode": "primary"},
                        "compare": {"mode": "compare-only"},
                    },
                    "source_compare": {"enabled": True, "max_price_deviation_pct": 0.3},
                }
            ),
        )

        result = registry.fetch_best_quotes(["161129"])

        self.assertEqual(result["161129"].meta.source, "primary")
        self.assertIn("source_conflict:compare", result["161129"].meta.warnings)
        self.assertEqual(result["161129"].meta.quality, "D")


if __name__ == "__main__":
    unittest.main()
