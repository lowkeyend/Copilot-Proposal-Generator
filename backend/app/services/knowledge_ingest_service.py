from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

from docx import Document
from fastapi import UploadFile

from app.services.qdrant_service import get_qdrant

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


def _clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _summary(text: str, limit: int = 12) -> str:
    words = text.split()
    if not words:
        return "Untitled chunk"
    head = " ".join(words[:limit])
    return head if len(words) <= limit else f"{head}..."


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 220) -> list[str]:
    sentences = _split_sentences(text)
    if not sentences:
        return [text] if text else []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        sent_len = len(sentence)
        if current and current_len + sent_len + 1 > chunk_size:
            chunk = " ".join(current).strip()
            if chunk:
                chunks.append(chunk)
            tail = chunk[-overlap:] if overlap > 0 else ""
            current = [tail, sentence] if tail else [sentence]
            current_len = sum(len(part) for part in current)
        else:
            current.append(sentence)
            current_len += sent_len + 1

    final = " ".join(current).strip()
    if final:
        chunks.append(final)
    return [_clean(chunk) for chunk in chunks if _clean(chunk)]


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    await file.seek(0)
    return data


def _extract_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    blocks = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))
    return _clean("\n".join(blocks))


def _extract_pdf(data: bytes) -> str:
    if PdfReader is None:
        raise RuntimeError("PDF support is unavailable because pypdf is not installed.")
    reader = PdfReader(io.BytesIO(data))
    return _clean("\n".join(page.extract_text() or "" for page in reader.pages))


def _extract_text(name: str, data: bytes) -> str:
    lower = name.lower()
    if lower.endswith(".docx"):
        return _extract_docx(data)
    if lower.endswith(".pdf"):
        return _extract_pdf(data)
    if lower.endswith((".txt", ".md")):
        return _clean(data.decode("utf-8", errors="ignore"))
    raise RuntimeError("Unsupported file type. Upload .docx, .pdf, .txt, or .md files.")


@dataclass
class ParsedDocument:
    filename: str
    text: str


class KnowledgeIngestService:
    async def parse_files(self, files: Iterable[UploadFile]) -> list[ParsedDocument]:
        parsed: list[ParsedDocument] = []
        for file in files:
            name = file.filename or "document"
            data = await _read_upload(file)
            text = _extract_text(name, data)
            if not text:
                continue
            parsed.append(ParsedDocument(filename=name, text=text))
        return parsed

    async def ingest_files(
        self,
        files: list[UploadFile],
        source_proposal: str,
        source_section: str,
        proposal_family: str,
    ) -> tuple[list[str], int]:
        parsed = await self.parse_files(files)
        if not parsed:
            raise RuntimeError("No readable content found in the uploaded files.")

        qdrant = get_qdrant()
        points = []
        filenames: list[str] = []

        for doc in parsed:
            filenames.append(doc.filename)
            chunks = _chunk_text(doc.text)
            for index, chunk in enumerate(chunks, start=1):
                payload = {
                    "text": chunk,
                    "chunk_text": chunk,
                    "chunk_summary": _summary(chunk),
                    "source_proposal": source_proposal or doc.filename,
                    "source_section": source_section or f"Upload chunk {index}",
                    "proposal_family": proposal_family or "Uploaded Knowledge",
                    "file": doc.filename,
                    "document_name": doc.filename,
                    "section": source_section or f"Upload chunk {index}",
                }
                points.append(
                    qdrant.build_point(
                        chunk_id=uuid4().hex,
                        text=chunk,
                        payload=payload,
                    )
                )

        qdrant.upsert_points(points)
        return filenames, len(points)


_ingest_singleton: KnowledgeIngestService | None = None


def get_knowledge_ingest() -> KnowledgeIngestService:
    global _ingest_singleton
    if _ingest_singleton is None:
        _ingest_singleton = KnowledgeIngestService()
    return _ingest_singleton
