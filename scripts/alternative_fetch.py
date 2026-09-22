"""OpenAlex and Crossref fallbacks for public paper metadata lookup.

Both providers are queried only after DBLP fails. The functions return the
project's normalized ``Paper`` records so the existing SQLite and analysis
pipeline can be reused without a second data model.
"""

from __future__ import annotations

import html
import os
import re
import ssl
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.dblp_fetch import DEFAULT_USER_AGENT, Paper


OPENALEX_URL = "https://api.openalex.org/works"
CROSSREF_URL = "https://api.crossref.org/works"
CONFERENCES = ("CVPR", "ICCV", "ECCV")
VENUE_ALIASES = {
    "CVPR": ("CVPR", "COMPUTER VISION AND PATTERN RECOGNITION"),
    "ICCV": ("ICCV", "INTERNATIONAL CONFERENCE ON COMPUTER VISION"),
    "ECCV": ("ECCV", "EUROPEAN CONFERENCE ON COMPUTER VISION"),
}


@dataclass(frozen=True)
class QuerySpec:
    text: str
    venue: str | None
    year: int | None


def parse_query(query: str) -> QuerySpec:
    venue_match = re.search(r"\bvenue:(CVPR|ICCV|ECCV)\b", query, re.I)
    year_match = re.search(r"\byear:(20\d{2})\b", query, re.I)
    text = re.sub(r"\b(?:venue:(?:CVPR|ICCV|ECCV)|year:20\d{2})\b", "", query, flags=re.I)
    return QuerySpec(
        text=" ".join(text.split()).strip(),
        venue=venue_match.group(1).upper() if venue_match else None,
        year=int(year_match.group(1)) if year_match else None,
    )


def _request_json(url: str, *, user_agent: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": user_agent},
        method="GET",
    )
    context = ssl.create_default_context()
    with urlopen(request, timeout=45, context=context) as response:
        return __import__("json").loads(response.read().decode("utf-8", errors="replace"))


def _matches(spec: QuerySpec, venue: str | None, year: int | None) -> bool:
    if spec.year and year != spec.year:
        return False
    if spec.venue:
        normalized_venue = (venue or "").upper()
        if not any(alias in normalized_venue for alias in VENUE_ALIASES.get(spec.venue, (spec.venue,))):
            return False
    return True


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words)) or None


def _openalex_paper(item: dict[str, Any], spec: QuerySpec) -> Paper | None:
    title = str(item.get("title") or "").strip()
    primary = item.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = source.get("display_name")
    year = item.get("publication_year")
    if not title or not _matches(spec, venue, year):
        return None
    concepts = [str(item.get("display_name")) for item in item.get("concepts", []) if item.get("display_name")]
    doi = item.get("doi")
    return Paper(
        title=title,
        authors=[str((author.get("author") or {}).get("display_name")) for author in item.get("authorships", []) if (author.get("author") or {}).get("display_name")],
        venue=venue,
        year=int(year) if year else None,
        doi=doi,
        dblp_url=None,
        electronic_edition=["https://doi.org/" + str(doi).removeprefix("https://doi.org/")] if doi else [],
        dblp_key="openalex:" + str(item.get("id") or title),
        paper_type="OpenAlex",
        abstract=_abstract_from_inverted_index(item.get("abstract_inverted_index")),
        keywords=concepts,
    )


def search_openalex(query: str, *, limit: int = 20, user_agent: str = DEFAULT_USER_AGENT) -> list[Paper]:
    spec = parse_query(query)
    params: dict[str, Any] = {"search": spec.text or query, "per-page": min(max(limit * 3, 1), 100)}
    if os.getenv("OPENALEX_EMAIL"):
        params["mailto"] = os.environ["OPENALEX_EMAIL"]
    payload = _request_json(f"{OPENALEX_URL}?{urlencode(params)}", user_agent=user_agent)
    return [paper for item in payload.get("results", []) if (paper := _openalex_paper(item, spec))][:limit]


def _crossref_year(item: dict[str, Any]) -> int | None:
    for field in ("published-print", "published-online", "issued", "created"):
        date_parts = (item.get(field) or {}).get("date-parts") or []
        if date_parts and date_parts[0]:
            try:
                return int(date_parts[0][0])
            except (TypeError, ValueError):
                return None
    return None


def _crossref_paper(item: dict[str, Any], spec: QuerySpec) -> Paper | None:
    title = str((item.get("title") or [""])[0]).strip()
    venue = str((item.get("container-title") or [""])[0]).strip() or None
    year = _crossref_year(item)
    if not title or not _matches(spec, venue, year):
        return None
    abstract = item.get("abstract")
    clean_abstract = re.sub(r"<[^>]+>", " ", html.unescape(str(abstract))) if abstract else None
    authors = [
        " ".join(part for part in (author.get("given"), author.get("family")) if part)
        for author in item.get("author", [])
    ]
    doi = item.get("DOI")
    return Paper(
        title=title,
        authors=authors,
        venue=venue,
        year=year,
        doi=doi,
        dblp_url=None,
        electronic_edition=[str(item.get("URL"))] if item.get("URL") else [],
        dblp_key="crossref:" + str(doi or title),
        paper_type="Crossref",
        abstract=clean_abstract,
        keywords=[str(value) for value in item.get("subject", [])],
    )


def search_crossref(query: str, *, limit: int = 20, user_agent: str = DEFAULT_USER_AGENT) -> list[Paper]:
    spec = parse_query(query)
    params: dict[str, Any] = {
        "query.bibliographic": spec.text or query,
        "rows": min(max(limit * 3, 1), 100),
        "select": "DOI,title,author,container-title,published-print,published-online,issued,created,URL,abstract,subject",
    }
    if os.getenv("CROSSREF_EMAIL"):
        params["mailto"] = os.environ["CROSSREF_EMAIL"]
    payload = _request_json(f"{CROSSREF_URL}?{urlencode(params)}", user_agent=user_agent)
    items = (payload.get("message") or {}).get("items", [])
    return [paper for item in items if (paper := _crossref_paper(item, spec))][:limit]


def search_with_fallback(query: str, *, limit: int, user_agent: str) -> tuple[str, list[Paper], list[str]]:
    """Query public metadata providers concurrently to reduce abstract latency."""
    errors: list[str] = []
    fetchers = {"OpenAlex": search_openalex, "Crossref": search_crossref}
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(fetch, query, limit=limit, user_agent=user_agent): name for name, fetch in fetchers.items()}
        for future in as_completed(pending):
            source = pending[future]
            try:
                papers = future.result()
                if papers:
                    return source, papers, errors
                errors.append(f"{source}: no matching records")
            except Exception as exc:
                errors.append(f"{source}: {exc}")
    return "fallback-empty", [], errors
