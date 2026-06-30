from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"FAIL: file not found: {path}")
        return 1

    with path.open("rb") as fh:
        files = [("files", (path.name, fh, "application/octet-stream"))]
        resp = httpx.post(f"{args.base_url.rstrip('/')}/parse-rfp", files=files, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    fields = data.get("fields", [])
    if len(fields) < 60:
        print(f"FAIL: expected at least 60 mapped fields, got {len(fields)}")
        return 1
    print(f"PASS: RFP parser returned {len(fields)} mapped fields")
    print(data.get("summary", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
