from __future__ import annotations

import io

from docx import Document

from app.services.docx_service import DocxComposer
from app.services.knowledge_ingest_service import _chunk_docx_document


def test_docx_ingest_uses_heading_sections() -> None:
    doc = Document()
    doc.add_heading("Scope of Work", level=1)
    doc.add_paragraph("This section covers upgrade analysis and environment preparation.")
    doc.add_heading("Testing", level=1)
    doc.add_paragraph("This section covers SIT, UAT, and rehearsal activities.")

    buffer = io.BytesIO()
    doc.save(buffer)

    chunks = _chunk_docx_document("sample.docx", buffer.getvalue())

    assert chunks
    assert any(chunk.section == "Scope of Work" for chunk in chunks)
    assert any(chunk.section == "Testing" for chunk in chunks)


def test_docx_render_sanitizer_removes_template_artifacts() -> None:
    composer = DocxComposer()
    cleaned = composer._sanitize_render_text(
        "<title>Solution</title>\n<paragraph>Body</paragraph>\n"
        "Word TOC field: Open in Word and refresh fields to populate page numbers.\n"
        "{{SECTION:Solution}}"
    )

    assert "<title>" not in cleaned.lower()
    assert "<paragraph>" not in cleaned.lower()
    assert "word toc field" not in cleaned.lower()
    assert "{{section:solution}}" not in cleaned.lower()
