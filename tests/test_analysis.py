import tempfile
import unittest
from pathlib import Path

from scripts.dblp_fetch import Paper
from src.storage import PaperStore


class AnalysisEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PaperStore(Path(self.temp_dir.name) / "papers.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_refresh_builds_topics_keywords_and_conference_trends(self):
        papers = [
            Paper(
                title="Vision Language Retrieval",
                authors=[], venue="CVPR", year=2024, doi=None,
                dblp_url=None, electronic_edition=[], dblp_key="a",
                paper_type="Conference", keywords=["vision-language", "retrieval"],
            ),
            Paper(
                title="Diffusion Video Generation",
                authors=[], venue="ICCV", year=2025, doi=None,
                dblp_url=None, electronic_edition=[], dblp_key="b",
                paper_type="Conference", keywords=["diffusion", "generation"],
            ),
            Paper(
                title="Temporary Imported Paper",
                authors=[], venue="ECCV", year=2025, doi=None,
                dblp_url=None, electronic_edition=[], dblp_key="c",
                paper_type="user-import", keywords=["temporary"],
            ),
        ]
        self.store.upsert_many(papers)

        summary = self.store.analysis_summary()
        self.assertEqual(summary["paper_count"], 3)
        self.assertGreaterEqual(summary["cluster_count"], 2)
        self.assertTrue(summary["topics"])
        self.assertTrue(any(item["keyword"] == "generation" for item in summary["keywords"]))
        self.assertEqual(len(self.store.keyword_papers("generation")), 1)

        trends = self.store.analysis_trends()
        self.assertEqual(trends["venues"], ["CVPR", "ICCV"])
        self.assertTrue(any(item["keyword"] == "generation" for item in trends["records"]))
        self.assertFalse(any(item["venue"] == "ECCV" for item in trends["records"]))


if __name__ == "__main__":
    unittest.main()
