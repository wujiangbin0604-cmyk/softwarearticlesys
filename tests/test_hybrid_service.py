import tempfile
import unittest
from pathlib import Path

from scripts.dblp_fetch import Paper
from src.hybrid_service import HybridPaperService
from src.storage import PaperStore


class HybridServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PaperStore(Path(self.temp_dir.name) / "papers.sqlite3")
        self.paper = Paper(
            title="Vision-Language Representation",
            authors=["A. Author"],
            venue="CVPR",
            year=2025,
            doi="10.1000/demo",
            dblp_url="https://dblp.org/rec/demo",
            electronic_edition=["https://example.org/demo"],
            dblp_key="conf/cvpr/Demo",
            paper_type="Conference",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_abstract_match_ignores_arxiv_prefix_and_rejects_wrong_title(self):
        exact = Paper(title="Large VLM-based Vision-Language-Action Models for Robotic Manipulation A Survey", authors=[], venue="", year=2025, doi=None, dblp_url=None, electronic_edition=[], dblp_key="exact", paper_type="OpenAlex", abstract="full abstract")
        wrong = Paper(title="Unrelated Vision Models", authors=[], venue="", year=2025, doi=None, dblp_url=None, electronic_edition=[], dblp_key="wrong", paper_type="OpenAlex", abstract="wrong abstract")
        self.assertEqual(HybridPaperService._best_abstract_match("2508.13073 Large VLM-based Vision-Language-Action Models for Robotic Manipulation A Survey", [wrong, exact]), exact)
        self.assertIsNone(HybridPaperService._best_abstract_match("A completely different paper", [wrong]))
    def test_local_search_is_used_before_remote(self):
        self.store.upsert_many([self.paper])
        service = HybridPaperService(self.store, online_enabled=False)
        result = service.search("vision-language", fetch_online=False)
        self.assertEqual(result["source"], "local")
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["papers"][0]["dblp_key"], "conf/cvpr/Demo")

    def test_imported_titles_are_searchable(self):
        service = HybridPaperService(self.store, online_enabled=False)
        service.import_titles(["Imported paper"], venue="ECCV", year=2024)
        result = service.search("imported", fetch_online=False)
        self.assertEqual(result["papers"][0]["venue"], "ECCV")


if __name__ == "__main__":
    unittest.main()
