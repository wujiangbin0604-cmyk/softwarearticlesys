import unittest

from app import is_valid_import_token


class ImportTokenTests(unittest.TestCase):
    def test_matching_token_is_accepted(self):
        self.assertTrue(is_valid_import_token("secret", "secret"))

    def test_missing_or_mismatched_token_is_rejected(self):
        self.assertFalse(is_valid_import_token(None, "secret"))
        self.assertFalse(is_valid_import_token("secret", None))
        self.assertFalse(is_valid_import_token("secret", "other"))


if __name__ == "__main__":
    unittest.main()
