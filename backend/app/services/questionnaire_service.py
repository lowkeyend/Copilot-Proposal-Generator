from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def load_questionnaire_questions() -> list[str]:
    candidates = [
        get_settings().assets_path / "questions.txt",
        Path(__file__).resolve().parents[3] / "data" / "questions.txt",
    ]
    for path in candidates:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="ignore")
            return [line.strip() for line in text.splitlines() if line.strip()]
    return []
