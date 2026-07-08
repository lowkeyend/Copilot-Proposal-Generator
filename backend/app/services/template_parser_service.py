from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from docx import Document

from app.config import get_settings
from app.models.schemas import (
    TemplateDocumentArtifact,
    TemplateImage,
    TemplateParagraph,
    TemplateSectionNode,
    TemplateTable,
)


def _is_heading(style_name: str) -> bool:
    return (style_name or "").strip().lower().startswith("heading")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _semantic_tags(title: str, text: str = "") -> list[str]:
    low = f"{title} {text}".lower()
    tags = []
    for needle in ("timeline", "governance", "solution", "scope", "methodology", "testing", "training", "assumption", "architecture", "migration", "security"):
        if needle in low:
            tags.append(needle)
    return list(dict.fromkeys(tags))


def parse_template_docx(path: str | Path, proposal_family: str = "") -> TemplateDocumentArtifact:
    path = Path(path)
    doc = Document(str(path))
    sections: list[TemplateSectionNode] = []
    current: TemplateSectionNode | None = None
    stack: list[TemplateSectionNode] = []
    table_index = 0
    image_index = 0
    metadata: dict[str, Any] = {"paragraphs": len(doc.paragraphs), "tables": len(doc.tables)}

    for para in doc.paragraphs:
        text = _clean(para.text)
        if not text:
            continue
        style_name = getattr(getattr(para, "style", None), "name", "") or ""
        if _is_heading(style_name):
            level_match = re.search(r"(\d+)$", style_name)
            level = int(level_match.group(1)) if level_match else 1
            node = TemplateSectionNode(title=text, level=level)
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].subsections.append(node)
            else:
                sections.append(node)
            stack.append(node)
            current = node
            continue
        target = stack[-1] if stack else current
        if target is None:
            continue
        target.paragraphs.append(TemplateParagraph(text=text, style=style_name, level=0))

    # Table metadata only; not a full cell-by-cell semantic parser yet.
    for idx, table in enumerate(doc.tables):
        caption = ""
        if idx < len(doc.paragraphs):
            prev = _clean(doc.paragraphs[max(0, idx - 1)].text)
            if len(prev) < 120:
                caption = prev
        rows = len(table.rows)
        cols = len(table.columns) if table.columns else 0
        target = sections[0] if sections else None
        table_node = TemplateTable(index=table_index, rows=rows, cols=cols, style="", caption=caption)
        table_index += 1
        if target:
            target.tables.append(table_node)
        metadata.setdefault("table_shapes", []).append({"rows": rows, "cols": cols})

    # Images are best-effort metadata from document relationships.
    for rel in doc.part.rels.values():
        if "image" not in getattr(rel, "target_ref", ""):
            continue
        target = sections[0] if sections else None
        image = TemplateImage(
            index=image_index,
            filename=Path(getattr(rel, "target_ref", "")).name,
            caption="",
            section=target.title if target else "",
            purpose="template",
            semantic_tags=_semantic_tags(target.title if target else "", ""),
        )
        image_index += 1
        if target:
            target.images.append(image)

    root = TemplateDocumentArtifact(
        name=path.stem,
        source_file=str(path),
        proposal_family=proposal_family or "General",
        sections=sections,
        images=[img for section in sections for img in section.images],
        metadata=metadata,
    )
    return root


def default_template_artifact() -> TemplateDocumentArtifact:
    settings = get_settings()
    path = settings.proposal_template_path
    if path.exists():
        return parse_template_docx(path, proposal_family="Temenos")
    return TemplateDocumentArtifact(name="empty-template", proposal_family="General")
