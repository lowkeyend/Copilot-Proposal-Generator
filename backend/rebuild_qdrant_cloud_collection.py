from __future__ import annotations

import argparse
from typing import Any

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
            batch.append(
                models.PointStruct(
                    id=point.id,
                    vector=models.Document(text=text, model=args.model),
                    payload=payload,
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
