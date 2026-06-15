"""Agent 9 — DOCX Composer.

Renders a reviewed proposal into a professional, branded Word document:
title page, auto-updating Table of Contents field, heading hierarchy,
markdown-ish body parsing (headings / bullets / simple pipe tables),
running header, and footer with page numbering.

Uses python-docx plus a few low-level OOXML fields (TOC + PAGE) that
python-docx doesn't expose directly.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from app.config import get_settings
from app.models.schemas import ClientContext, SectionResult

BRAND = RGBColor(0x1F, 0x3A, 0x5F)  # deep navy
ACCENT = RGBColor(0x2E, 0x6F, 0x8E)


def _set_cell_text(cell, text: str, bold: bool = False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text)
    run.bold = bold


def _add_field(paragraph, instruction: str) -> None:
    """Insert a Word field (e.g. TOC, PAGE) into a paragraph."""
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(fld_end)


class DocxComposer:
    def __init__(self) -> None:
        self.settings = get_settings()

    # ------------------------------------------------------------------
    def compose(
        self,
        title: str,
        context: ClientContext,
        sections: list[SectionResult],
        proposal_id: Optional[str] = None,
    ) -> Path:
        doc = Document()
        self._configure_styles(doc)
        self._add_header_footer(doc, title)
        self._add_title_page(doc, title, context)
        self._add_toc(doc)
        self._add_sections(doc, sections)

        self.settings.generated_path.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "proposal"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe}_{stamp}.docx"
        out_path = self.settings.generated_path / filename
        doc.save(str(out_path))
        return out_path

    # ------------------------------------------------------------------
    def _configure_styles(self, doc: Document) -> None:
        normal = doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        for level, size in ((1, 16), (2, 13), (3, 11.5)):
            try:
                h = doc.styles[f"Heading {level}"]
                h.font.color.rgb = BRAND
                h.font.size = Pt(size)
                h.font.bold = True
            except KeyError:
                continue

    def _add_header_footer(self, doc: Document, title: str) -> None:
        section = doc.sections[0]

        header_p = section.header.paragraphs[0]
        header_p.text = title
        header_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if header_p.runs:
            header_p.runs[0].font.size = Pt(8)
            header_p.runs[0].font.color.rgb = ACCENT

        footer_p = section.footer.paragraphs[0]
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_p.add_run("Page ").font.size = Pt(8)
        _add_field(footer_p, "PAGE")
        footer_p.add_run(" of ").font.size = Pt(8)
        _add_field(footer_p, "NUMPAGES")

    def _add_title_page(
        self, doc: Document, title: str, context: ClientContext
    ) -> None:
        for _ in range(4):
            doc.add_paragraph()
        t = doc.add_paragraph()
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = t.add_run(title)
        run.bold = True
        run.font.size = Pt(30)
        run.font.color.rgb = BRAND

        if context.client_name:
            sub = doc.add_paragraph()
            sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = sub.add_run(f"Prepared for {context.client_name}")
            r.font.size = Pt(15)
            r.font.color.rgb = ACCENT

        meta_lines = [
            ("Industry", context.industry),
            ("Engagement", context.project_type),
            ("Date", datetime.now().strftime("%d %B %Y")),
        ]
        for _ in range(3):
            doc.add_paragraph()
        for label, value in meta_lines:
            if not value:
                continue
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run(f"{label}: ").bold = True
            p.add_run(value)
        doc.add_page_break()

    def _add_toc(self, doc: Document) -> None:
        heading = doc.add_paragraph("Table of Contents")
        heading.style = doc.styles["Heading 1"]
        p = doc.add_paragraph()
        # TOC field across heading levels 1-3; updates on open / F9 in Word.
        _add_field(p, 'TOC \\o "1-3" \\h \\z \\u')
        doc.add_page_break()

    def _add_sections(self, doc: Document, sections: list[SectionResult]) -> None:
        for section in sections:
            doc.add_heading(section.title, level=1)
            self._render_markdownish(doc, section.content)
            doc.add_paragraph()

    # ------------------------------------------------------------------
    def _render_markdownish(self, doc: Document, content: str) -> None:
        """Render a lightweight subset of markdown the LLM tends to produce."""
        lines = content.splitlines()
        i = 0
        table_buffer: list[str] = []

        def flush_table() -> None:
            nonlocal table_buffer
            rows = [r for r in table_buffer if r.strip()]
            # Drop separator rows like |---|---|
            rows = [r for r in rows if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", r)]
            if not rows:
                table_buffer = []
                return
            parsed = [
                [c.strip() for c in r.strip().strip("|").split("|")] for r in rows
            ]
            cols = max(len(r) for r in parsed)
            table = doc.add_table(rows=0, cols=cols)
            table.style = "Light Grid Accent 1"
            for ridx, row in enumerate(parsed):
                cells = table.add_row().cells
                for cidx in range(cols):
                    val = row[cidx] if cidx < len(row) else ""
                    _set_cell_text(cells[cidx], val, bold=(ridx == 0))
            table_buffer = []

        while i < len(lines):
            line = lines[i].rstrip()
            if "|" in line and line.strip().startswith("|"):
                table_buffer.append(line)
                i += 1
                continue
            if table_buffer:
                flush_table()

            stripped = line.strip()
            if not stripped:
                i += 1
                continue
            if stripped.startswith("### "):
                doc.add_heading(stripped[4:], level=3)
            elif stripped.startswith("## "):
                doc.add_heading(stripped[3:], level=2)
            elif stripped.startswith("# "):
                doc.add_heading(stripped[2:], level=2)
            elif re.match(r"^[-*]\s+", stripped):
                p = doc.add_paragraph(style="List Bullet")
                self._add_inline(p, re.sub(r"^[-*]\s+", "", stripped))
            elif re.match(r"^\d+[.)]\s+", stripped):
                p = doc.add_paragraph(style="List Number")
                self._add_inline(p, re.sub(r"^\d+[.)]\s+", "", stripped))
            else:
                p = doc.add_paragraph()
                self._add_inline(p, stripped)
            i += 1

        if table_buffer:
            flush_table()

    def _add_inline(self, paragraph, text: str) -> None:
        """Handle **bold** spans inline."""
        parts = re.split(r"(\*\*[^*]+\*\*)", text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                paragraph.add_run(part[2:-2]).bold = True
            elif part:
                paragraph.add_run(part)


_composer_singleton: Optional[DocxComposer] = None


def get_composer() -> DocxComposer:
    global _composer_singleton
    if _composer_singleton is None:
        _composer_singleton = DocxComposer()
    return _composer_singleton
