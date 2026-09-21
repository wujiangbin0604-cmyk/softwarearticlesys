#!/usr/bin/env python3
"""Import completed local PDF files as paper metadata records."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.dblp_fetch import Paper
from src.storage import PaperStore


DEFAULT_COLLECTIONS = ("CV 2024 综述", "CV 2025 综述", "ICCV2025")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local PDF titles and refresh analytics")
    parser.add_argument("--root", type=Path, default=Path(r"D:\百度网盘"))
    parser.add_argument("--db", type=Path, default=Path("data/visionpulse.sqlite3"))
    parser.add_argument("--limit", type=int, default=0, help="0 imports all matching PDFs")
    return parser.parse_args()


def clean_title(path: Path) -> str:
    title = path.stem.replace("_", " ")
    title = re.sub(r"\b(?:CVPR|ICCV|ECCV)\s+20\d{2}\s+paper\b.*$", "", title, flags=re.I)
    return " ".join(title.split()).strip(" ._-")


def infer_metadata(path: Path) -> tuple[str | None, int | None]:
    text = str(path).upper()
    venue_match = re.search(r"(CVPR|ICCV|ECCV)(?=\D|20\d{2})", text)
    year_match = re.search(r"(20\d{2})", text)
    venue = venue_match.group(1) if venue_match else None
    year = int(year_match.group(1)) if year_match else None
    return venue, year


def iter_pdfs(root: Path):
    if root.name in DEFAULT_COLLECTIONS:
        roots = [root]
    else:
        roots = [root / name for name in DEFAULT_COLLECTIONS if (root / name).is_dir()]
    for collection in roots:
        for path in sorted(collection.rglob("*.pdf")):
            if ".baiduyun." not in path.name.casefold() and path.is_file():
                yield path


def build_paper(path: Path) -> Paper:
    venue, year = infer_metadata(path)
    fingerprint = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]
    return Paper(
        title=clean_title(path),
        authors=[],
        venue=venue,
        year=year,
        doi=None,
        dblp_url=None,
        electronic_edition=[path.resolve().as_uri()],
        dblp_key=f"local-pdf:{fingerprint}",
        paper_type="local-pdf",
        abstract=None,
        keywords=[],
    )


def main() -> None:
    args = parse_args()
    paths = list(iter_pdfs(args.root))
    if args.limit > 0:
        paths = paths[: args.limit]
    papers = [build_paper(path) for path in paths if clean_title(path)]
    store = PaperStore(args.db)
    imported = store.upsert_many(papers, source_query=f"local-pdf:{args.root.resolve()}")
    summary = store.analysis_summary()
    print(f"Imported {imported} PDF records into {args.db.resolve()}")
    print(
        f"Analysis refreshed: papers={summary['paper_count']} "
        f"clusters={summary['cluster_count']} run_at={summary['run_at']}"
    )


if __name__ == "__main__":
    main()
