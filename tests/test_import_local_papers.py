import tempfile
import unittest
from pathlib import Path

from scripts.import_local_papers import build_paper, clean_title, infer_metadata, iter_pdfs


class LocalPaperImportTests(unittest.TestCase):
    def test_clean_title_removes_export_suffix(self):
        path = Path("Vision Transformers CVPR 2024 paper_review.pdf")
        self.assertEqual(clean_title(path), "Vision Transformers")

    def test_infer_metadata_reads_venue_and_year_from_path(self):
        venue, year = infer_metadata(Path("ICCV2025/object_tracking.pdf"))
        self.assertEqual((venue, year), ("ICCV", 2025))

    def test_iter_pdfs_skips_incomplete_baiduyun_files(self):
        with tempfile.TemporaryDirectory() as directory:
            collection = Path(directory) / "ICCV2025"
            collection.mkdir()
            (collection / "finished.pdf").write_bytes(b"pdf")
            (collection / "unfinished.pdf.baiduyun.downloading").write_bytes(b"partial")

            self.assertEqual([path.name for path in iter_pdfs(Path(directory))], ["finished.pdf"])

    def test_build_paper_has_stable_local_key(self):
        paper = build_paper(Path("CV 2025 综述/ICCV2025 retrieval.pdf"))
        self.assertTrue(paper.dblp_key.startswith("local-pdf:"))
        self.assertEqual(paper.paper_type, "local-pdf")


if __name__ == "__main__":
    unittest.main()

