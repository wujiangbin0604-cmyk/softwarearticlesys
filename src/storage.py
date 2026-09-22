"""SQLite storage for the local paper cache."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from scripts.dblp_fetch import Paper


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,
    authors_json TEXT NOT NULL DEFAULT '[]',
    venue TEXT,
    year INTEGER,
    doi TEXT,
    dblp_url TEXT,
    electronic_edition_json TEXT NOT NULL DEFAULT '[]',
    dblp_key TEXT,
    paper_type TEXT,
    abstract TEXT,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    source_query TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(dblp_key),
    UNIQUE(doi)
);
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title_normalized);
CREATE INDEX IF NOT EXISTS idx_papers_venue_year ON papers(venue, year);
"""


def normalize_title(title: str) -> str:
    return " ".join(title.casefold().split())


class PaperStore:
    """Small persistence boundary used by both batch and on-demand flows."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def connection(self):
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(SCHEMA)

    def upsert_many(self, papers: Iterable[Paper], source_query: str | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for paper in papers:
            rows.append(
                (
                    paper.title,
                    normalize_title(paper.title),
                    json.dumps(paper.authors, ensure_ascii=False),
                    paper.venue,
                    paper.year,
                    paper.doi,
                    paper.dblp_url,
                    json.dumps(paper.electronic_edition, ensure_ascii=False),
                    paper.dblp_key,
                    paper.paper_type,
                    paper.abstract,
                    json.dumps(paper.keywords or [], ensure_ascii=False),
                    source_query,
                    now,
                )
            )
        if not rows:
            return 0
        with self.connection() as connection:
            connection.executemany(
                """
                INSERT INTO papers (
                    title, title_normalized, authors_json, venue, year, doi,
                    dblp_url, electronic_edition_json, dblp_key, paper_type,
                    abstract, keywords_json, source_query, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dblp_key) DO UPDATE SET
                    title=excluded.title,
                    title_normalized=excluded.title_normalized,
                    authors_json=excluded.authors_json,
                    venue=excluded.venue,
                    year=excluded.year,
                    doi=excluded.doi,
                    dblp_url=excluded.dblp_url,
                    electronic_edition_json=excluded.electronic_edition_json,
                    paper_type=excluded.paper_type,
                    abstract=excluded.abstract,
                    keywords_json=excluded.keywords_json,
                    source_query=excluded.source_query,
                    fetched_at=excluded.fetched_at
                """,
                rows,
            )
            connection.commit()
        self.refresh_analysis()
        return len(rows)

    def refresh_analysis(self) -> dict:
        from src.analysis import AnalysisEngine

        return AnalysisEngine(self).refresh()

    def analysis_summary(self, limit: int = 10) -> dict:
        from src.analysis import AnalysisEngine

        return AnalysisEngine(self).summary(limit)

    def keyword_papers(self, keyword: str, limit: int = 50) -> list[dict]:
        from src.analysis import AnalysisEngine

        return AnalysisEngine(self).papers_for_keyword(keyword, limit)

    def analysis_trends(self, keywords: list[str] | None = None) -> dict:
        from src.analysis import AnalysisEngine

        return AnalysisEngine(self).trends(keywords)

    def search(self, query: str, *, exact: bool = False, limit: int = 50) -> list[dict]:
        normalized = normalize_title(query)
        if exact:
            sql = "SELECT * FROM papers WHERE title_normalized = ? ORDER BY year DESC LIMIT ?"
            params = (normalized, limit)
        else:
            sql = """
                SELECT * FROM papers
                WHERE title_normalized LIKE ?
                   OR lower(COALESCE(venue, '')) LIKE ?
                   OR lower(COALESCE(dblp_key, '')) LIKE ?
                   OR lower(COALESCE(keywords_json, '')) LIKE ?
                ORDER BY year DESC, title ASC LIMIT ?
            """
            wildcard = f"%{normalized}%"
            params = (wildcard, wildcard, wildcard, wildcard, limit)
        with self.connection() as connection:
            return [self._row_to_dict(row) for row in connection.execute(sql, params)]

    def all(self, limit: int = 1000) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM papers ORDER BY year DESC, title ASC LIMIT ?", (limit,)
            )
            return [self._row_to_dict(row) for row in rows]

    def update_paper(self, paper_id: int, *, title: str, venue: str | None,
                     year: int | None, keywords: list[str]) -> dict | None:
        title = title.strip()
        if not title:
            raise ValueError("title is required")
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE papers
                SET title = ?, title_normalized = ?, venue = ?, year = ?, keywords_json = ?, fetched_at = ?
                WHERE id = ?
                """,
                (title, normalize_title(title), venue, year,
                 json.dumps(keywords, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), paper_id),
            )
            row = connection.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
            connection.commit()
        if row is None:
            return None
        self.refresh_analysis()
        return self._row_to_dict(row)

    def delete_paper(self, paper_id: int) -> bool:
        with self.connection() as connection:
            cursor = connection.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
            deleted = cursor.rowcount
            connection.commit()
        if deleted:
            self.refresh_analysis()
        return bool(deleted)
    def delete_by_source_query(self, source_query: str) -> int:
        """Delete records created by one controlled import/search operation."""
        with self.connection() as connection:
            cursor = connection.execute("DELETE FROM papers WHERE source_query = ?", (source_query,))
            deleted = cursor.rowcount
            connection.commit()
        if deleted:
            self.refresh_analysis()
        return int(deleted)
    def count(self) -> int:
        with self.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0])

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["authors"] = json.loads(data.pop("authors_json"))
        data["electronic_edition"] = json.loads(data.pop("electronic_edition_json"))
        data["keywords"] = json.loads(data.pop("keywords_json"))
        return data

