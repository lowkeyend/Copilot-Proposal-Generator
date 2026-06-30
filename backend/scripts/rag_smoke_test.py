from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--document", default="Maidaan Ledger - Technical Proposal.pdf")
    parser.add_argument(
        "--question",
        default="What does the document say about implementation phases?",
    )
    args = parser.parse_args()

    payload = {
        "question": args.question,
        "document_names": [args.document],
        "top_k": 5,
    }
    resp = httpx.post(f"{args.base_url.rstrip('/')}/query-docs", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    evidence = data.get("evidence", [])
    used_documents = data.get("used_documents", [])
    if not evidence:
        print("FAIL: no evidence returned")
        return 1
    if not any(args.document.lower() in str(item).lower() for item in used_documents):
        print("FAIL: target document not used")
        return 1
    print("PASS: doc query returned evidence and the target document was used")
    print(data.get("answer", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
