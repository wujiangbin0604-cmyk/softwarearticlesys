import unittest

from scripts.alternative_fetch import (
    _abstract_from_inverted_index,
    _matches,
    parse_query,
)


class AlternativeFetchTests(unittest.TestCase):
    def test_parse_query_extracts_filters(self):
        spec = parse_query("representation venue:cvpr year:2025")
        self.assertEqual(spec.text, "representation")
        self.assertEqual(spec.venue, "CVPR")
        self.assertEqual(spec.year, 2025)

    def test_abstract_index_is_reconstructed(self):
        self.assertEqual(
            _abstract_from_inverted_index({"vision": [1], "Learning": [0]}),
            "Learning vision",
        )

    def test_filters_match_venue_and_year(self):
        spec = parse_query("venue:ICCV year:2024")
        self.assertTrue(_matches(spec, "IEEE/CVF International Conference on Computer Vision", 2024))
        self.assertFalse(_matches(spec, "CVPR", 2024))


if __name__ == "__main__":
    unittest.main()
