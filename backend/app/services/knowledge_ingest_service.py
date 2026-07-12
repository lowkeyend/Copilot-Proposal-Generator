from __future__ import annotations

import io
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4
from zipfile import ZipFile

from docx import Document
from fastapi import UploadFile

from app.config import get_settings
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


def _chunk_text(text: str, chunk_size: int = 420, overlap: int = 70) -> list[str]:
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
            current_len += sent_len + 1

    final = " ".join(current).strip()
    if final:
        chunks.append(final)
    return [_clean(chunk) for chunk in chunks if _clean(chunk)]


def _batched(items: list, size: int = 16):
    for index in range(0, len(items), size):
        yield items[index : index + size]


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


def _is_heading_paragraph(paragraph) -> bool:
    style_name = ((getattr(paragraph.style, "name", "") or "").strip()).lower()
    if not style_name:
        return False
    return style_name.startswith("heading") or style_name in {"title", "subtitle"}


def _extract_docx_sections(data: bytes) -> list[tuple[str, str]]:
    doc = Document(io.BytesIO(data))
    sections: list[tuple[str, str]] = []
    current_heading = "Document Overview"
    current_blocks: list[str] = []

    def flush() -> None:
        nonlocal current_blocks
        body = _clean("\n".join(current_blocks))
        if body:
            sections.append((current_heading, body))
        current_blocks = []

    for paragraph in doc.paragraphs:
        text = _clean(paragraph.text or "")
        if not text:
            continue
        if _is_heading_paragraph(paragraph):
            flush()
            current_heading = text
            continue
        current_blocks.append(text)

    for table in doc.tables:
        current_blocks.extend(
            " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            for row in table.rows
            if any(cell.text.strip() for cell in row.cells)
        )

    flush()
    return sections or [("Document Overview", _extract_docx(data))]


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "document"


def _extract_docx_images(filename: str, data: bytes) -> list[str]:
    settings = get_settings()
    base = _safe_name(Path(filename).stem)
    image_dir = settings.assets_path / "document-images" / base
    image_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            media = [
                name
                for name in archive.namelist()
                if name.startswith("word/media/")
                and not name.endswith("/")
            ]
            for idx, member in enumerate(media, start=1):
                ext = Path(member).suffix.lower() or ".bin"
                target = image_dir / f"image_{idx:02d}{ext}"
                target.write_bytes(archive.read(member))
                saved.append(str(target))
    except Exception:
        return []
    return saved


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


def _chunk_generic_document(name: str, text: str) -> list[ParsedChunk]:
    section = Path(name).stem or "Document Overview"
    chunks = _chunk_text(text)
    return [
        ParsedChunk(
            text=chunk,
            section=section,
            summary=f"{section}: {_summary(chunk, limit=10)}",
        )
        for chunk in chunks
    ]


def _chunk_docx_document(name: str, data: bytes) -> list[ParsedChunk]:
    parsed: list[ParsedChunk] = []
    for heading, body in _extract_docx_sections(data):
        for chunk in _chunk_text(body):
            parsed.append(
                ParsedChunk(
                    text=chunk,
                    section=heading or "Document Overview",
                    summary=f"{heading or 'Document Overview'}: {_summary(chunk, limit=10)}",
                )
            )
    return parsed or _chunk_generic_document(name, _extract_docx(data))


@dataclass
class ParsedDocument:
    filename: str
    text: str
    image_paths: list[str]
    raw_bytes: bytes


@dataclass
class ParsedChunk:
    text: str
    section: str
    summary: str


class KnowledgeIngestService:
    async def parse_files(self, files: Iterable[UploadFile]) -> list[ParsedDocument]:
        parsed: list[ParsedDocument] = []
        for file in files:
            name = file.filename or "document"
            data = await _read_upload(file)
            text = _extract_text(name, data)
            if not text:
                continue
            images = _extract_docx_images(name, data) if name.lower().endswith(".docx") else []
            parsed.append(ParsedDocument(filename=name, text=text, image_paths=images, raw_bytes=data))
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
            chunks = (
                _chunk_docx_document(doc.filename, doc.raw_bytes)
                if doc.filename.lower().endswith(".docx")
                else _chunk_generic_document(doc.filename, doc.text)
            )
            for index, chunk in enumerate(chunks, start=1):
                payload = {
                    "text": chunk.text,
                    "chunk_text": chunk.text,
                    "chunk_summary": chunk.summary,
                    "source_proposal": source_proposal or doc.filename,
                    "source_section": source_section or chunk.section or f"Upload chunk {index}",
                    "proposal_family": proposal_family or "Uploaded Knowledge",
                    "file": doc.filename,
                    "document_name": doc.filename,
                    "section": source_section or chunk.section or f"Upload chunk {index}",
                    "image_paths": doc.image_paths,
                }
                points.append(
                    qdrant.build_point(
                        chunk_id=uuid4().hex,
                        text=chunk.text,
                        payload=payload,
                    )
                )

        for batch in _batched(points, size=16):
            qdrant.upsert_points(batch)
        return filenames, len(points)


_ingest_singleton: KnowledgeIngestService | None = None


def get_knowledge_ingest() -> KnowledgeIngestService:
    global _ingest_singleton
    if _ingest_singleton is None:
        _ingest_singleton = KnowledgeIngestService()
    return _ingest_singleton
