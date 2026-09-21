"""Local-first paper search with DBLP as an on-demand fallback."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict

from scripts.dblp_fetch import DEFAULT_USER_AGENT, iter_query_hits
from src.storage import PaperStore, normalize_title


class HybridPaperService:
    """Search SQLite first; query DBLP only when the local cache misses."""

    def __init__(
        self,
        store: PaperStore,
        *,
        online_enabled: bool = True,
        request_sleep: float = 1.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.store = store
        self.online_enabled = online_enabled
        self.request_sleep = request_sleep
        self.user_agent = user_agent
        self.last_remote_request = 0.0

    def search(
        self,
        query: str,
        *,
        exact: bool = False,
        limit: int = 20,
        fetch_online: bool = True,
    ) -> dict:
        query = query.strip()
        if not query:
            return {"source": "local", "cache_hit": True, "papers": self.store.all(limit)}

        local = self.store.search(query, exact=exact, limit=limit)
        if local or not (fetch_online and self.online_enabled):
            return {"source": "local", "cache_hit": bool(local), "papers": local}

        self._respect_rate_limit()
        papers, _ = iter_query_hits(
            query,
            limit=limit,
            sleep_seconds=self.request_sleep,
            user_agent=self.user_agent,
        )
        self.last_remote_request = time.monotonic()
        self.store.upsert_many(papers, source_query=query)
        return {
            "source": "dblp",
            "cache_hit": False,
            "papers": [self.store._row_to_dict(row) for row in self.store.search(query, limit=limit)],
            "remote_count": len(papers),
        }

    def import_titles(self, titles: list[str], venue: str = "CVPR", year: int = 2025) -> int:
        """Import titles as searchable placeholders until metadata enrichment runs."""
        from scripts.dblp_fetch import Paper

        papers = [
            Paper(
                title=title.strip(),
                authors=[],
                venue=venue,
                year=year,
                doi=None,
                dblp_url=None,
                electronic_edition=[],
                dblp_key="user-import:" + hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()[:24],
                paper_type="user-import",
            )
            for title in titles
            if title.strip()
        ]
        return self.store.upsert_many(papers, source_query="user-import")

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self.last_remote_request
        remaining = self.request_sleep - elapsed
        if remaining > 0:
            time.sleep(remaining)
