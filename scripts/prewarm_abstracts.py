"""Populate missing abstracts once and keep them in the server SQLite cache."""

from __future__ import annotations

import argparse
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.alternative_fetch import search_with_fallback
from scripts.dblp_fetch import DEFAULT_USER_AGENT
from src.hybrid_service import HybridPaperService
from src.storage import PaperStore


def fetch(title: str):
    source, papers, errors = search_with_fallback(title, limit=3, user_agent=DEFAULT_USER_AGENT)
    match = HybridPaperService._best_abstract_match(title, papers)
    return source, match, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache missing abstracts in SQLite")
    parser.add_argument("--sqlite", type=Path, default=Path("data/visionpulse.sqlite3"))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    connection = sqlite3.connect(args.sqlite)
    rows = connection.execute(
        """
        SELECT id, title FROM papers
        WHERE abstract IS NULL OR length(trim(abstract)) = 0
        ORDER BY CASE WHEN venue IN ('CVPR','ICCV','ECCV') THEN 0 ELSE 1 END,
                 year DESC, id
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    connection.close()

    store = PaperStore(args.sqlite)
    cached = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        jobs = {pool.submit(fetch, title): (paper_id, title) for paper_id, title in rows}
        for future in as_completed(jobs):
            paper_id, _ = jobs[future]
            try:
                _, paper, _ = future.result()
            except Exception:
                continue
            if paper and paper.abstract:
                store.update_abstract(paper_id, paper.abstract, paper.keywords or None)
                cached += 1

    print(f"checked={len(rows)} cached={cached}")


if __name__ == "__main__":
    main()
