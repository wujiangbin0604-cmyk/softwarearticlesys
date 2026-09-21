#!/usr/bin/env python3
"""Export the local SQLite paper records for migration to a remote service."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Export VisionPulse papers as JSON")
    parser.add_argument("--db", type=Path, default=Path("data/visionpulse.sqlite3"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = PaperStore(args.db).all(limit=100000)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"papers": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"exported={len(records)} output={args.output.resolve()}")


if __name__ == "__main__":
    main()
