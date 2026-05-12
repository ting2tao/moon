import unittest


class ProviderTests(unittest.TestCase):
    def test_infers_market_prefix_and_preserves_explicit_prefix(self):
        from providers import infer_market_prefix, normalize_code

        self.assertEqual(infer_market_prefix("161129"), "sz")
        self.assertEqual(infer_market_prefix("501018"), "sh")
        self.assertEqual(normalize_code("sz161129"), ("sz", "161129"))
        self.assertEqual(normalize_code("SH501018"), ("sh", "501018"))

    def test_normalizes_jisilu_lof_row(self):
        from providers import normalize_jisilu_lof_row

        row = normalize_jisilu_lof_row(
            {
                "id": "161129",
                "cell": {
                    "fund_id": "161129",
                    "fund_nm": "原油LOF易方达",
                    "price": "1.234",
                    "discount_rt": "2.34%",
                    "amount": "850.5",
                    "apply_status": "开放申购",
                    "redeem_status": "开放赎回",
                },
            }
        )

        self.assertEqual(row["code"], "161129")
        self.assertEqual(row["name"], "原油LOF易方达")
        self.assertEqual(row["product_type"], "LOF")
        self.assertEqual(row["market_price"], 1.234)
        self.assertEqual(row["premium_rate"], 2.34)
        self.assertEqual(row["turnover_amount"], 8_505_000)
        self.assertEqual(row["subscription_status"], "开放申购")


if __name__ == "__main__":
    unittest.main()
