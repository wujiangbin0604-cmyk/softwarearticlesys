#!/usr/bin/env python3
"""Minimal local-first HTTP API for the VisionPulse prototype."""

from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.hybrid_service import HybridPaperService
from src.storage import PaperStore


ROOT = Path(__file__).resolve().parent


def parse_limit(raw_value: str, default: int = 50, maximum: int = 100) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(value, 1), maximum)



class ApiHandler(BaseHTTPRequestHandler):
    service: HybridPaperService

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # prototype.html is opened from file://, which sends the browser origin as null.
        # Keep the local demo usable without exposing the API to arbitrary websites.
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self._send_json({"error": "Not found"}, status=404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_OPTIONS(self) -> None:  # noqa: N802 - browser preflight for JSON POST
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.end_headers()
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API name
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/prototype.html"):
            self._send_file(ROOT / "prototype.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/intro-research-bg.png":
            self._send_file(ROOT / "intro-research-bg.png", "image/png")
            return

        if parsed.path == "/api/health":
            self._send_json({"ok": True, "cache_count": self.service.store.count()})
            return
        if parsed.path.startswith("/api/papers/") and parsed.path.endswith("/abstract"):
            try:
                paper_id = int(parsed.path.split("/")[3])
                self._send_json(self.service.enrich_abstract(paper_id))
            except (ValueError, TypeError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=502)
            return
        if parsed.path == "/api/papers":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            exact = params.get("exact", ["0"])[0] == "1"
            online = params.get("online", ["1"])[0] == "1"
            try:
                self._send_json(self.service.search(query, exact=exact, fetch_online=online))
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=502)
            return
        if parsed.path == "/api/analytics/summary":
            try:
                self._send_json(self.service.store.analysis_summary())
            except Exception as exc:  # keep the frontend diagnostic instead of a dropped proxy connection
                self._send_json({"error": "analysis unavailable", "detail": str(exc)}, status=500)
            return
        if parsed.path == "/api/analytics/keywords":
            params = parse_qs(parsed.query)
            keyword = params.get("keyword", [""])[0].strip().casefold()
            limit = parse_limit(params.get("limit", ["50"])[0])
            try:
                self._send_json({"keyword": keyword, "papers": self.service.store.keyword_papers(keyword, limit)})
            except Exception as exc:
                self._send_json({"error": "analysis unavailable", "detail": str(exc)}, status=500)
            return
        if parsed.path == "/api/analytics/trends":
            params = parse_qs(parsed.query)
            raw_keywords = params.get("keywords", [""])[0]
            keywords = [item.strip() for item in raw_keywords.split(",") if item.strip()]
            try:
                self._send_json(self.service.store.analysis_trends(keywords or None))
            except Exception as exc:
                self._send_json({"error": "analysis unavailable", "detail": str(exc)}, status=500)
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API name
        if urlparse(self.path).path == "/api/papers/update":
            expected_token = os.getenv("IMPORT_TOKEN")
            if not is_valid_import_token(expected_token, self.headers.get("X-Import-Token")):
                self._send_json({"error": "update requires a valid IMPORT_TOKEN"}, status=401)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                paper_id = int(body.get("id"))
                raw_keywords = body.get("keywords", [])
                keywords = raw_keywords if isinstance(raw_keywords, list) else [item.strip() for item in str(raw_keywords).split(",") if item.strip()]
                updated = self.service.store.update_paper(
                    paper_id,
                    title=str(body.get("title", "")),
                    venue=str(body.get("venue") or "") or None,
                    year=int(body["year"]) if body.get("year") not in (None, "") else None,
                    keywords=[str(item) for item in keywords if str(item).strip()],
                )
                if updated is None:
                    self._send_json({"error": "paper not found"}, status=404)
                else:
                    self._send_json({"paper": updated})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if urlparse(self.path).path == "/api/papers/delete":
            expected_token = os.getenv("IMPORT_TOKEN")
            if not is_valid_import_token(expected_token, self.headers.get("X-Import-Token")):
                self._send_json({"error": "delete requires a valid IMPORT_TOKEN"}, status=401)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                paper_id = int(body.get("id"))
                if not self.service.store.delete_paper(paper_id):
                    self._send_json({"error": "paper not found"}, status=404)
                else:
                    self._send_json({"deleted": True, "id": paper_id})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if urlparse(self.path).path == "/api/papers/purge-source-query":
            expected_token = os.getenv("IMPORT_TOKEN")
            provided_token = self.headers.get("X-Import-Token")
            if not is_valid_import_token(expected_token, provided_token):
                self._send_json({"error": "purge requires a valid IMPORT_TOKEN"}, status=401)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                source_query = str(body.get("source_query", "")).strip()
                if not source_query:
                    raise ValueError("source_query is required")
                count = self.service.store.delete_by_source_query(source_query)
                self._send_json({"deleted": count, "source_query": source_query})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if urlparse(self.path).path == "/api/papers/import-records":
            expected_token = os.getenv("IMPORT_TOKEN")
            provided_token = self.headers.get("X-Import-Token")
            if not is_valid_import_token(expected_token, provided_token):
                self._send_json({"error": "bulk import requires a valid IMPORT_TOKEN"}, status=401)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                records = body.get("papers", [])
                if not isinstance(records, list):
                    raise ValueError("papers must be a JSON array")
                count = self.service.import_records(records)
                self._send_json({"imported": count, "source": "bulk-import"}, status=201)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if urlparse(self.path).path != "/api/papers/import":
            self._send_json({"error": "Not found"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            titles = body.get("titles", [])
            if not isinstance(titles, list):
                raise ValueError("titles must be a JSON array")
            count = self.service.import_titles(
                [str(title) for title in titles],
                venue=str(body.get("venue", "CVPR")),
                year=int(body.get("year", 2025)),
            )
            self._send_json({"imported": count, "source": "user-import"}, status=201)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args) -> None:
        print(format % args)


def is_valid_import_token(expected: str | None, provided: str | None) -> bool:
    return bool(expected) and bool(provided) and hmac.compare_digest(expected, provided)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the VisionPulse local-first API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=Path("data/visionpulse.sqlite3"))
    parser.add_argument("--no-online", action="store_true", help="disable DBLP fallback")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = PaperStore(args.db)
    ApiHandler.service = HybridPaperService(store, online_enabled=not args.no_online)
    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"VisionPulse API listening at http://{args.host}:{args.port}")
    print(f"SQLite cache: {Path(args.db).resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()




