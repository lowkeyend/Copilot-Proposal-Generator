from __future__ import annotations

import argparse
import re
from typing import Any
from uuid import uuid4

from qdrant_client import QdrantClient, models

from app.config import get_settings

TEXT_KEYS = ("text", "chunk", "content", "body", "passage", "chunk_text")


def _first(payload: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            if isinstance(value, list):
                return " > ".join(str(item) for item in value)
            return str(value)
    return default


def _chunk_text(text: str, chunk_size: int = 650, overlap: int = 120) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return [text] if text.strip() else []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current and current_len + len(sentence) + 1 > chunk_size:
            chunk = " ".join(current).strip()
            if chunk:
                chunks.append(chunk)
            tail: list[str] = []
            tail_len = 0
            for prior in reversed(current):
                if tail_len + len(prior) > overlap:
                    break
                tail.insert(0, prior)
                tail_len += len(prior)
            current = [*tail, sentence]
            current_len = sum(len(part) for part in current)
        else:
            current.append(sentence)
            current_len += len(sentence) + 1
    final = " ".join(current).strip()
    if final:
        chunks.append(final)
    return chunks


def _summary(text: str) -> str:
    words = text.split()
    head = " ".join(words[:12])
    return head if len(words) <= 12 else f"{head}..."


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a new Qdrant Cloud collection using Qdrant Cloud Inference."
    )
    parser.add_argument("--source", required=True, help="Existing collection name.")
    parser.add_argument("--target", required=True, help="New collection name to create.")
    parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Qdrant Cloud inference model to use.",
    )
    parser.add_argument("--vector-size", type=int, default=384)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    settings = get_settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        cloud_inference=True,
    )

    existing = {c.name for c in client.get_collections().collections}
    if args.target in existing:
        raise RuntimeError(
            f"Target collection '{args.target}' already exists. Choose a new target."
        )

    client.create_collection(
        collection_name=args.target,
        vectors_config=models.VectorParams(
            size=args.vector_size,
            distance=models.Distance.COSINE,
        ),
    )

    total = client.count(collection_name=args.source, exact=True).count
    print(
        f"Copying {total} points from '{args.source}' to '{args.target}' using {args.model}"
    )

    offset = None
    processed = 0
    skipped = 0

    while True:
        points, offset = client.scroll(
            collection_name=args.source,
            with_payload=True,
            with_vectors=False,
            limit=args.batch_size,
            offset=offset,
        )
        if not points:
            break

        batch: list[models.PointStruct] = []
        for point in points:
            payload = dict(point.payload or {})
            text = _first(payload, TEXT_KEYS)
            if not text:
                skipped += 1
                continue
            for index, chunk in enumerate(_chunk_text(text), start=1):
                next_payload = {
                    **payload,
                    "text": chunk,
                    "chunk_text": chunk,
                    "chunk_summary": _summary(chunk),
                    "parent_point_id": str(point.id),
                    "rechunk_index": index,
                }
                batch.append(
                    models.PointStruct(
                        id=uuid4().hex,
                        vector=models.Document(text=chunk, model=args.model),
                        payload=next_payload,
                    )
                )

        if batch:
            client.upsert(collection_name=args.target, points=batch, wait=True)
            processed += len(batch)
            print(f"Processed {processed}/{total}")

        if offset is None:
            break

    print(f"Done. Wrote {processed} points, skipped {skipped} points with no text.")


if __name__ == "__main__":
    main()
