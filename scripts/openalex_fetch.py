"""Collect CVPR/ICCV/ECCV metadata without using DBLP."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.alternative_fetch import search_crossref, search_openalex
from src.storage import PaperStore

VENUES = ("CVPR", "ICCV", "ECCV")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch conference metadata from OpenAlex/Crossref")
    parser.add_argument("--venue", nargs="+", choices=VENUES, default=list(VENUES))
    parser.add_argument("--year", nargs="+", type=int, default=[2022, 2023, 2024, 2025])
    parser.add_argument("--limit-per-source", type=int, default=100)
    parser.add_argument("--sqlite", type=Path, default=Path("data/visionpulse.sqlite3"))
    args = parser.parse_args()
    store = PaperStore(args.sqlite)
    imported = 0
    for venue in args.venue:
        for year in args.year:
            query = f"{venue} computer vision {year}"
            records = []
            for fetch in (search_openalex, search_crossref):
                try:
                    records.extend(fetch(query, limit=args.limit_per_source))
                except Exception as exc:
                    print(f"{fetch.__name__} failed for {query}: {exc}")
            filtered = [
                item for item in records
                if item.year == year and venue in (item.venue or "").upper()
            ]
            for item in filtered:
                if not item.venue:
                    item.venue = venue
            imported += store.upsert_many(filtered, source_query=f"{venue}:{year}:openalex-crossref")
            print(f"{venue} {year}: {len(filtered)} records")
    print(f"imported={imported}")


if __name__ == "__main__":
    main()
