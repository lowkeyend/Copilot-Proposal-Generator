"""Small shared helpers."""

import re


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "").strip("_")
    return slug or fallback
