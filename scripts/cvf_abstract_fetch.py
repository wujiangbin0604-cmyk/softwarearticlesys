#!/usr/bin/env python3
"""Fill missing abstracts by matching paper titles against CVF OpenAccess."""
import difflib
import io
import re
import time
import urllib.request
from html.parser import HTMLParser

from pypdf import PdfReader
from src.storage import PaperStore

MAX_PAPERS = 200
USER_AGENT = "VisionPulse/1.0 CVF abstract importer"


class PaperLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items, self.href, self.text = [], None, []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href", "") if tag == "a" else ""
        if href.endswith("_paper.html"):
            self.href, self.text = href, []

    def handle_data(self, data):
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.items.append((" ".join("".join(self.text).split()), self.href))
            self.href = None


def normalize(value):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).split())


def download(url, accept="*/*"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def extract_abstract(data):
    text = " ".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages[:2])
    text = re.sub(r"\s+", " ", text)
    match = re.search(r"Abstract\s*:?\s*(.*?)\s+(?:1\s*\.?\s*Introduction|Introduction)\b", text, re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip(" .:-") if match else None


def load_index():
    records = []
    for venue in ("CVPR", "ICCV", "ECCV"):
        for year in (2022, 2023, 2024, 2025):
            try:
                parser = PaperLinks()
                parser.feed(download(f"https://openaccess.thecvf.com/{venue}{year}?day=all").decode("utf-8", "replace"))
                for title, href in parser.items:
                    page = "https://openaccess.thecvf.com" + href if href.startswith("/") else "https://openaccess.thecvf.com/" + href
                    records.append((normalize(title), page.replace("/html/", "/papers/").replace(".html", ".pdf"), venue, year))
                print(venue, year, len(parser.items))
            except Exception as exc:
                print("index failed", venue, year, exc)
    return records


def main():
    index = load_index()
    store = PaperStore("/app/data/visionpulse.sqlite3")
    rows = [row for row in store.all(10000) if row.get("title") and not row.get("abstract")][:MAX_PAPERS]
    success = missing = failed = 0
    for number, row in enumerate(rows, 1):
        title = normalize(row["title"])
        best = max(index, key=lambda item: difflib.SequenceMatcher(None, title, item[0]).ratio(), default=None)
        score = difflib.SequenceMatcher(None, title, best[0]).ratio() if best else 0
        if not best or score < 0.88:
            missing += 1
            print(number, "unmatched", row["title"][:70])
            continue
        try:
            abstract = extract_abstract(download(best[1], "application/pdf"))
            if abstract:
                store.update_abstract(row["id"], abstract, row.get("keywords") or [])
                success += 1
                print(number, "ok", best[2], best[3], round(score, 2), row["title"][:60])
            else:
                missing += 1
        except Exception as exc:
            failed += 1
            print(number, "failed", exc)
        time.sleep(2)
    store.refresh_analysis()
    print(f"finished ok={success} unmatched_or_empty={missing} failed={failed}")


if __name__ == "__main__":
    main()
