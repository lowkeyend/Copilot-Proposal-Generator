from __future__ import annotations

import argparse
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.config import get_settings
from app.services.embedding_service import get_embedder

TEXT_KEYS = ("text", "chunk", "content", "body", "passage", "chunk_text")


def _first(payload: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            if isinstance(value, list):
                return " > ".join(str(item) for item in value)
            return str(value)
    return default


def _vector_size(collection_info: Any) -> int:
    vectors = collection_info.config.params.vectors
    if hasattr(vectors, "size"):
        return int(vectors.size)
    if isinstance(vectors, dict):
        first = next(iter(vectors.values()))
        return int(first.size)
    raise RuntimeError("Could not determine vector size from Qdrant collection config.")


def _client() -> QdrantClient:
    settings = get_settings()
    if settings.use_qdrant_cloud:
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return QdrantClient(path=str(settings.qdrant_local_path))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-embed all existing Qdrant chunks using the configured embedding provider."
    )
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    settings = get_settings()
    client = _client()
    embedder = get_embedder()
    collection = settings.qdrant_collection

    info = client.get_collection(collection_name=collection)
    expected_size = _vector_size(info)
    total = client.count(collection_name=collection, exact=True).count
    print(
        f"Re-embedding {total} chunks in '{collection}' using "
        f"{settings.embedding_provider}:{settings.embedding_model}"
    )

    offset = None
    processed = 0
    skipped = 0
    checked_size = False

    while True:
        points, offset = client.scroll(
            collection_name=collection,
            with_payload=True,
            with_vectors=False,
            limit=args.batch_size,
            offset=offset,
        )
        if not points:
            break

        rows: list[tuple[Any, dict[str, Any], str]] = []
        for point in points:
            payload = dict(point.payload or {})
            text = _first(payload, TEXT_KEYS)
            if not text:
                skipped += 1
                continue
            rows.append((point.id, payload, text))

        if rows:
            texts = [row[2] for row in rows]
            vectors = embedder.embed_texts(texts)
            if not checked_size:
                actual_size = len(vectors[0])
                if actual_size != expected_size:
                    raise RuntimeError(
                        f"Embedding dimension mismatch. Collection expects {expected_size}, "
                        f"but provider returned {actual_size}. Use a model with the same "
                        "dimension or recreate the collection."
                    )
                checked_size = True

            client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(id=point_id, vector=vector, payload=payload)
                    for (point_id, payload, _text), vector in zip(rows, vectors)
                ],
                wait=True,
            )
            processed += len(rows)
            print(f"Processed {processed}/{total} chunks")

        if offset is None:
            break

    print(f"Done. Re-embedded {processed} chunks, skipped {skipped} chunks with no text.")


if __name__ == "__main__":
    main()
