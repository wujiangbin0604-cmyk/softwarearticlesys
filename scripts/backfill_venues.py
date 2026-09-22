"""Backfill missing CVPR/ICCV/ECCV labels for locally imported papers.

The local PDF import path often has no conference field. This script uses the
DBLP title search endpoint to recover a conference label without changing the
paper title, abstract, keywords, or source metadata.
"""

from __future__ import annotations

import argparse
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.dblp_fetch import DEFAULT_USER_AGENT, iter_query_hits

VENUES = ("CVPR", "ICCV", "ECCV")


def infer(title: str) -> tuple[str, int | None] | None:
    try:
        hits, _ = iter_query_hits(title, limit=3, sleep_seconds=0, user_agent=DEFAULT_USER_AGENT)
    except Exception:
        return None
    target = " ".join(title.casefold().split())
    for hit in hits:
        candidate = " ".join((hit.title or "").casefold().split())
        if candidate != target:
            continue
        venue = (hit.venue or "").upper()
        matched = next((item for item in VENUES if item in venue), None)
        if matched:
            return matched, hit.year
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=Path, default=Path("data/visionpulse.sqlite3"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    connection = sqlite3.connect(args.sqlite)
    rows = connection.execute(
        "SELECT id, title FROM papers WHERE venue IS NULL OR trim(venue) = '' LIMIT ?",
        (args.limit,),
    ).fetchall()
    updated = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        jobs = {pool.submit(infer, title): (paper_id, title) for paper_id, title in rows}
        for future in as_completed(jobs):
            paper_id, _ = jobs[future]
            result = future.result()
            if not result:
                continue
            venue, year = result
            if year:
                connection.execute("UPDATE papers SET venue=?, year=COALESCE(year, ?) WHERE id=?", (venue, year, paper_id))
            else:
                connection.execute("UPDATE papers SET venue=? WHERE id=?", (venue, paper_id))
            updated += 1
    connection.commit()
    connection.close()
    print(f"checked={len(rows)} updated={updated}")


if __name__ == "__main__":
    main()
