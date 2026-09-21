#!/usr/bin/env python3
"""Download publication metadata from DBLP's official Search API.

DBLP Search API reference:
https://dblp.org/faq/How+to+use+the+dblp+search+API.html

This collector intentionally stores bibliographic metadata only. DBLP does not
guarantee abstracts or author supplied keywords in Search API responses, so
those fields are left as None for a later enrichment step.
"""

from __future__ import annotations

import argparse
import json
import logging
import ssl
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:
    certifi = None


API_URL = "https://dblp.org/search/publ/api"
DEFAULT_USER_AGENT = (
    "VisionPulse/0.1 (course project; DBLP metadata collector; "
    "contact: replace-with-your-email@example.com)"
)
MAX_PAGE_SIZE = 1000
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class Paper:
    """Normalized fields consumed by the later keyword-analysis pipeline."""

    title: str
    authors: list[str]
    venue: str | None
    year: int | None
    doi: str | None
    dblp_url: str | None
    electronic_edition: list[str]
    dblp_key: str | None
    paper_type: str | None
    abstract: str | None = None
    keywords: list[str] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch CVPR/ICCV/ECCV publication metadata from DBLP."
    )
    parser.add_argument(
        "--venue",
        nargs="+",
        choices=("CVPR", "ICCV", "ECCV"),
        default=["CVPR", "ICCV", "ECCV"],
        help="venues to collect (default: all three), case-sensitive choices",
    )
    parser.add_argument(
        "--year",
        nargs="+",
        type=int,
        default=list(range(2022, datetime.now().year + 1)),
        help="publication years to collect (default: 2022 through current year)",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="custom DBLP query; repeat this option for multiple queries",
    )
    parser.add_argument(
        "--limit-per-query",
        type=int,
        default=1000,
        help="maximum hits per query, capped at DBLP's 1000-hit API limit",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="seconds between API requests (default: 1.0)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/dblp_papers.json"),
        help="normalized JSON output path",
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        help="optional path for the unmodified DBLP JSON responses",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        help="optional SQLite cache path to populate alongside JSON",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="descriptive User-Agent sent to DBLP",
    )
    return parser.parse_args()


def build_queries(args: argparse.Namespace) -> list[str]:
    if args.query:
        return args.query
    return [f"venue:{venue} year:{year}" for venue in args.venue for year in args.year]


def request_json(
    query: str,
    *,
    offset: int,
    limit: int,
    user_agent: str,
    retries: int = 4,
) -> dict[str, Any]:
    params = {
        "q": query,
        "format": "json",
        "h": min(max(limit, 1), MAX_PAGE_SIZE),
        "f": max(offset, 0),
        "c": 0,
    }
    url = f"{API_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": user_agent,
        },
        method="GET",
    )

    ssl_context = (
        ssl.create_default_context(cafile=certifi.where())
        if certifi is not None
        else ssl.create_default_context()
    )

    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=45, context=ssl_context) as response:
                body = response.read().decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")
                if "json" not in content_type.lower():
                    preview = " ".join(body[:240].split())
                    raise RuntimeError(
                        f"DBLP returned non-JSON content ({content_type or 'unknown'}): {preview}"
                    )
                return json.loads(body)
        except HTTPError as exc:
            retryable = exc.code in RETRYABLE_STATUS_CODES
            if not retryable or attempt == retries:
                raise RuntimeError(f"DBLP request failed with HTTP {exc.code}: {url}") from exc
            wait = min(30.0, 2.0**attempt)
            logging.warning("DBLP returned HTTP %s; retrying in %.1fs", exc.code, wait)
            time.sleep(wait)
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries:
                raise RuntimeError(f"DBLP request failed: {url}") from exc
            wait = min(30.0, 2.0**attempt)
            logging.warning("DBLP request error (%s); retrying in %.1fs", exc, wait)
            time.sleep(wait)

    raise AssertionError("unreachable")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalize_hit(hit: dict[str, Any]) -> Paper | None:
    info = hit.get("info") or {}
    title = str(info.get("title") or "").strip()
    if not title:
        return None

    authors: list[str] = []
    author_data = info.get("authors", {}).get("author", [])
    for author in as_list(author_data):
        if isinstance(author, dict):
            name = author.get("text") or author.get("name")
        else:
            name = author
        if name:
            authors.append(str(name).strip())

    year_value = info.get("year")
    try:
        year = int(year_value) if year_value else None
    except (TypeError, ValueError):
        year = None

    electronic_edition = []
    for entry in as_list(info.get("ee")):
        if isinstance(entry, dict):
            value = entry.get("text") or entry.get("href")
        else:
            value = entry
        if value:
            electronic_edition.append(str(value))

    return Paper(
        title=title,
        authors=authors,
        venue=info.get("venue"),
        year=year,
        doi=info.get("doi"),
        dblp_url=info.get("url"),
        electronic_edition=electronic_edition,
        dblp_key=info.get("key"),
        paper_type=info.get("type"),
    )


def iter_query_hits(
    query: str,
    *,
    limit: int,
    sleep_seconds: float,
    user_agent: str,
) -> tuple[list[Paper], list[dict[str, Any]]]:
    page_size = min(max(limit, 1), MAX_PAGE_SIZE)
    offset = 0
    papers: list[Paper] = []
    raw_pages: list[dict[str, Any]] = []

    while len(papers) < limit:
        payload = request_json(
            query,
            offset=offset,
            limit=min(page_size, limit - len(papers)),
            user_agent=user_agent,
        )
        raw_pages.append(payload)
        result = payload.get("result") or {}
        hits = result.get("hits") or {}
        total = int(hits.get("@total", 0) or 0)
        page_hits = hits.get("hit") or []
        page_papers = [paper for hit in as_list(page_hits) if (paper := normalize_hit(hit))]
        papers.extend(page_papers)
        logging.info("query=%r offset=%d received=%d total=%d", query, offset, len(page_papers), total)

        if not page_hits or offset + len(page_hits) >= total:
            break
        offset += len(page_hits)
        time.sleep(max(0.0, sleep_seconds))

    return papers[:limit], raw_pages


def deduplicate(papers: Iterable[Paper]) -> list[Paper]:
    unique: dict[str, Paper] = {}
    for paper in papers:
        identity = (paper.dblp_key or paper.doi or paper.title.lower()).strip()
        unique.setdefault(identity, paper)
    return list(unique.values())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.limit_per_query < 1:
        raise SystemExit("--limit-per-query must be greater than 0")

    queries = build_queries(args)
    collected: list[Paper] = []
    raw_pages: list[dict[str, Any]] = []
    for index, query in enumerate(queries):
        papers, pages = iter_query_hits(
            query,
            limit=args.limit_per_query,
            sleep_seconds=args.sleep,
            user_agent=args.user_agent,
        )
        collected.extend(papers)
        raw_pages.extend(pages)
        if index < len(queries) - 1:
            time.sleep(max(0.0, args.sleep))

    unique = deduplicate(collected)
    output = {
        "source": "DBLP Search API",
        "source_url": API_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "queries": queries,
        "count": len(unique),
        "papers": [asdict(paper) for paper in unique],
    }
    write_json(args.output, output)
    if args.sqlite:
        from src.storage import PaperStore

        PaperStore(args.sqlite).upsert_many(unique, source_query="batch:" + ",".join(queries))
    if args.raw_output:
        write_json(args.raw_output, {"source": API_URL, "pages": raw_pages})
    logging.info("saved %d unique papers to %s", len(unique), args.output)


if __name__ == "__main__":
    main()
