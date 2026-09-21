#!/usr/bin/env python3
"""Upload an exported paper JSON file to the protected Render endpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload exported papers to VisionPulse")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--url", required=True, help="Render base URL")
    parser.add_argument("--token", required=True, help="IMPORT_TOKEN configured on Render")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    papers = payload.get("papers", payload) if isinstance(payload, dict) else payload
    if not isinstance(papers, list):
        raise ValueError("input JSON must be a list or an object with a papers array")
    if args.batch_size < 1:
        raise ValueError("batch-size must be positive")

    endpoint = args.url.rstrip("/") + "/api/papers/import-records"
    total = 0
    for start in range(0, len(papers), args.batch_size):
        batch = papers[start : start + args.batch_size]
        body = json.dumps({"papers": batch}, ensure_ascii=False).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Import-Token": args.token,
            },
        )
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
        total += int(result.get("imported", 0))
        print(f"uploaded={min(start + len(batch), len(papers))}/{len(papers)}")
    print(f"imported={total}")


if __name__ == "__main__":
    main()
