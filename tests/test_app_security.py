import unittest

from app import is_valid_import_token, parse_limit


class ImportTokenTests(unittest.TestCase):
    def test_matching_token_is_accepted(self):
        self.assertTrue(is_valid_import_token("secret", "secret"))

    def test_analytics_limit_is_bounded_and_invalid_values_use_default(self):
        self.assertEqual(parse_limit("250"), 100)
        self.assertEqual(parse_limit("0"), 1)
        self.assertEqual(parse_limit("bad"), 50)

    def test_missing_or_mismatched_token_is_rejected(self):
        self.assertFalse(is_valid_import_token(None, "secret"))
        self.assertFalse(is_valid_import_token("secret", None))
        self.assertFalse(is_valid_import_token("secret", "other"))


if __name__ == "__main__":
    unittest.main()


