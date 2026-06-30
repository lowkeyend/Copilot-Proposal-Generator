from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import httpx


BAD_ANSWER_MARKERS = (
    "retrieved evidence",
    "evidence block",
    "chunk",
    "document:",
    "[1]",
    "[2]",
    "core banking capabilities",
    "digital channels and integrations",
)


@dataclass(frozen=True)
class RagCase:
    question: str
    document: str | None = None
    max_words: int = 130


CASES = [
    RagCase(
        question=(
            "What exact Phase 1 and Phase 2 products, interfaces, and channels "
            "are in scope? Do not give general categories."
        ),
        max_words=170,
    ),
    RagCase(
        question=(
            "Compare phase 1 and phase 2 scope for products, channels, "
            "interfaces, and implementation approach."
        ),
        max_words=140,
    ),
    RagCase(
        question=(
            "What database, hosting model, reporting platform, and target "
            "customer or transaction volume are specified?"
        ),
        max_words=120,
    ),
    RagCase(
        question=(
            "What are the key implementation stages, responsibilities, and "
            "risks that must be clarified before proposal submission?"
        ),
        max_words=140,
    ),
]


def _validate_answer(answer: str, max_words: int) -> list[str]:
    failures: list[str] = []
    words = answer.split()
    lower = answer.lower()
    if not answer.strip():
        failures.append("empty answer")
    if len(words) > max_words:
        failures.append(f"answer too long ({len(words)} words)")
    for marker in BAD_ANSWER_MARKERS:
        if marker in lower:
            failures.append(f"leaked internal marker: {marker}")
    if len(answer) > 280 and "." not in answer:
        failures.append("looks like an unsynthesized excerpt")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--document", default="")
    args = parser.parse_args()

    failures: list[str] = []
    with httpx.Client(timeout=160) as client:
        for idx, case in enumerate(CASES, 1):
            document_names = [case.document or args.document] if (case.document or args.document) else []
            payload = {
                "question": case.question,
                "document_names": document_names,
                "top_k": 8,
            }
            resp = client.post(f"{args.base_url.rstrip('/')}/query-docs", json=payload)
            try:
                resp.raise_for_status()
            except Exception as exc:
                failures.append(f"case {idx}: request failed: {exc}")
                continue
            data = resp.json()
            answer = str(data.get("answer", ""))
            evidence = data.get("evidence", [])
            if not evidence:
                failures.append(f"case {idx}: no evidence returned")
            failures.extend(f"case {idx}: {item}" for item in _validate_answer(answer, case.max_words))
            print(f"CASE {idx}: {answer}")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nPASS: RAG answers are synthesized, concise, and evidence-backed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
