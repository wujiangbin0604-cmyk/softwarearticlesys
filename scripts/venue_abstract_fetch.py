"""Fill missing abstracts from CVF, ECVA, then OpenAlex.

The module is safe to call from the API startup path: it only updates rows
whose abstract is empty and uses a strict title match before writing.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


USER_AGENT = "VisionPulse/1.0 abstract importer"
CVF_YEARS = {"CVPR": (2022, 2023, 2024, 2025), "ICCV": (2023, 2025)}
ECCV_YEARS = (2022, 2024)


def normalize(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8", "replace")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.href:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href:
            title = " ".join("".join(self.parts).split())
            if title:
                self.links.append((title, self.href))
            self.href = None


class AbstractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        marker = f"{attrs_map.get('id', '')} {attrs_map.get('class', '')}".lower()
        if self.depth:
            if tag == "div":
                self.depth += 1
        elif tag == "div" and "abstract" in marker:
            self.depth = 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.depth and tag == "div":
            self.depth -= 1

    def result(self) -> str:
        text = " ".join(" ".join(self.parts).split())
        return re.sub(r"^Abstract\s*:?[\s-]*", "", text, flags=re.I).strip()


def build_index() -> dict[tuple[str, int], str]:
    index: dict[tuple[str, int], str] = {}
    for venue, years in CVF_YEARS.items():
        for year in years:
            base = f"https://openaccess.thecvf.com/{venue}{year}?day=all"
            try:
                parser = LinkParser()
                parser.feed(fetch_text(base))
                for title, href in parser.links:
                    if href.endswith("_paper.html"):
                        index[normalize(title)] = urllib.parse.urljoin(base, href)
            except Exception as exc:
                print(f"CVF {venue}{year} failed: {exc}")
            time.sleep(1)

    try:
        parser = LinkParser()
        base = "https://www.ecva.net/papers.php"
        parser.feed(fetch_text(base))
        for title, href in parser.links:
            match = re.search(r"papers/eccv_(2022|2024)/.*_paper\.php", href, re.I)
            if match:
                index[normalize(title)] = urllib.parse.urljoin(base, href)
    except Exception as exc:
        print(f"ECVA failed: {exc}")
    return index


def openalex_abstract(title: str, year: int | None, doi: str | None) -> str | None:
    params: dict[str, str | int] = {"search": title, "per-page": 5}
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    request = urllib.request.Request(
        "https://api.openalex.org/works?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.load(response)
    wanted_doi = (doi or "").removeprefix("https://doi.org/").casefold()
    for work in payload.get("results", []):
        score = difflib.SequenceMatcher(None, normalize(title), normalize(work.get("title"))).ratio()
        work_doi = (work.get("doi") or "").removeprefix("https://doi.org/").casefold()
        if score < 0.92:
            continue
        if wanted_doi and work_doi and wanted_doi != work_doi:
            continue
        positions = work.get("abstract_inverted_index") or {}
        words = sorted((position, word) for word, slots in positions.items() for position in slots)
        if words:
            return " ".join(word for _, word in words)
    return None


def refresh_missing(db_path: Path | str, limit: int = 10) -> dict[str, int]:
    db = sqlite3.connect(db_path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT id, title, venue, year, doi FROM papers "
            "WHERE abstract IS NULL OR trim(abstract) = '' ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return {"checked": 0, "updated": 0, "failed": 0}
        index = build_index()
        updated = failed = 0
        for row in rows:
            try:
                abstract = None
                key = normalize(row["title"])
                if key and key in index:
                    parser = AbstractParser()
                    parser.feed(fetch_text(index[key]))
                    abstract = parser.result()
                if not abstract:
                    abstract = openalex_abstract(row["title"], row["year"], row["doi"])
                if abstract and len(abstract) >= 80:
                    db.execute("UPDATE papers SET abstract = ? WHERE id = ? AND (abstract IS NULL OR trim(abstract) = '')", (abstract, row["id"]))
                    db.commit()
                    updated += 1
            except Exception as exc:
                failed += 1
                print(f"abstract refresh failed for {row['title'][:60]}: {exc}")
            time.sleep(1)
        return {"checked": len(rows), "updated": updated, "failed": failed}
    finally:
        db.close()


if __name__ == "__main__":
    path = Path(os.getenv("VISIONPULSE_DB", "data/visionpulse.sqlite3"))
    print(refresh_missing(path, int(os.getenv("ABSTRACT_REFRESH_LIMIT", "10"))))

