"""Pydantic schemas shared across the API surface.

These mirror the request/response contracts consumed by the Next.js
frontend. Keeping them in one place keeps the API self-documenting via
FastAPI's generated OpenAPI schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _uid() -> str:
    return uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Client context (Agent 1)
# --------------------------------------------------------------------------
class ClientContext(BaseModel):
    client_name: str = ""
    industry: str = ""
    project_type: str = ""
    client_profile: Literal["established", "greenfield", "unknown"] = "established"
    implementation_context: str = "Modernization / migration for an existing institution"
    canonical_product: str = "Temenos Transact"
    tone: str = "Formal"
    special_instructions: str = ""


class GenerateContextRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    # Optional hints from Page-1 form fields; the agent will respect them.
    client_name: Optional[str] = None
    industry: Optional[str] = None
    project_type: Optional[str] = None
    client_profile: Optional[Literal["established", "greenfield", "unknown"]] = None
    implementation_context: Optional[str] = None
    canonical_product: Optional[str] = None


class GenerateContextResponse(BaseModel):
    context: ClientContext
    proposal_family: str
    family_confidence: float = 0.0
    family_rationale: str = ""


# --------------------------------------------------------------------------
# Templates / patterns (Agents 3 & 4)
# --------------------------------------------------------------------------
class TemplateSection(BaseModel):
    title: str
    # Retrieval hint keywords used by the Retrieval Agent for this section.
    keywords: list[str] = Field(default_factory=list)
    description: str = ""


class ProposalTemplate(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str
    proposal_family: str
    sections: list[TemplateSection] = Field(default_factory=list)
    # "discovered" = learned from corpus, "user" = created/edited in UI.
    origin: Literal["discovered", "user"] = "discovered"
    support: int = 0  # how many corpus proposals this pattern was seen in
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class SuggestTemplateRequest(BaseModel):
    prompt: str
    context: ClientContext
    proposal_family: str
    model: Optional[str] = None


class SuggestTemplateResponse(BaseModel):
    suggested: ProposalTemplate
    alternatives: list[ProposalTemplate] = Field(default_factory=list)


# --------------------------------------------------------------------------
# TOC (Agent 5)
# --------------------------------------------------------------------------
class TocSection(BaseModel):
    id: str = Field(default_factory=_uid)
    title: str
    keywords: list[str] = Field(default_factory=list)
    description: str = ""


class BuildTocRequest(BaseModel):
    prompt: str
    context: ClientContext
    proposal_family: str
    template: Optional[ProposalTemplate] = None
    model: Optional[str] = None


class BuildTocResponse(BaseModel):
    toc: list[TocSection]


# --------------------------------------------------------------------------
# Retrieval (Agent 6)
# --------------------------------------------------------------------------
class EvidenceChunk(BaseModel):
    text: str
    score: float
    summary: str = ""
    source_proposal: str = ""
    source_section: str = ""
    proposal_family: str = ""
    chunk_id: str = ""
    source_type: str = "document"


class KnowledgeBaseChunk(BaseModel):
    chunk_id: str
    summary: str = ""
    text: str = ""
    source_proposal: str = ""
    source_section: str = ""
    proposal_family: str = ""
    score: float = 0.0
    payload: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseChunkUpdate(BaseModel):
    text: Optional[str] = None
    source_proposal: Optional[str] = None
    source_section: Optional[str] = None
    proposal_family: Optional[str] = None


# --------------------------------------------------------------------------
# Section generation (Agents 7 & 6 combined per-section)
# --------------------------------------------------------------------------
class GenerateSectionRequest(BaseModel):
    section_title: str
    keywords: list[str] = Field(default_factory=list)
    context: ClientContext
    proposal_family: str
    prompt: str = ""
    pattern_guidance: str = ""
    # Free-form instruction for targeted regeneration, e.g. "make it shorter".
    instruction: str = ""
    model: Optional[str] = None
    top_k: int = 6
    include_temenos_official: bool = False
    use_hybrid_retrieval: bool = True
    detail_level: Literal["balanced", "corpus", "exhaustive"] = "corpus"
    require_evidence: bool = True


class SectionResult(BaseModel):
    id: str = Field(default_factory=_uid)
    title: str
    content: str
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    locked: bool = False
    model: str = ""
    generated_at: str = Field(default_factory=_now)


class GenerateProposalRequest(BaseModel):
    prompt: str
    context: ClientContext
    proposal_family: str
    toc: list[TocSection]
    model: Optional[str] = None
    top_k: int = 6
    include_temenos_official: bool = False
    use_hybrid_retrieval: bool = True
    detail_level: Literal["balanced", "corpus", "exhaustive"] = "corpus"
    require_evidence: bool = True


class GenerateProposalResponse(BaseModel):
    proposal_id: str
    version_id: str
    sections: list[SectionResult]


# --------------------------------------------------------------------------
# Consistency review (Agent 8)
# --------------------------------------------------------------------------
class ReviewIssue(BaseModel):
    severity: Literal["info", "warning", "error"] = "warning"
    category: str
    message: str
    section_title: str = ""


class ReviewProposalRequest(BaseModel):
    context: ClientContext
    sections: list[SectionResult]
    model: Optional[str] = None


class ReviewProposalResponse(BaseModel):
    issues: list[ReviewIssue]
    summary: str = ""


# --------------------------------------------------------------------------
# Persistence / versioning
# --------------------------------------------------------------------------
class ProposalVersion(BaseModel):
    version_id: str = Field(default_factory=_uid)
    created_at: str = Field(default_factory=_now)
    label: str = ""
    sections: list[SectionResult] = Field(default_factory=list)


class ProposalRecord(BaseModel):
    proposal_id: str = Field(default_factory=_uid)
    title: str = ""
    prompt: str = ""
    context: ClientContext = Field(default_factory=ClientContext)
    proposal_family: str = ""
    toc: list[TocSection] = Field(default_factory=list)
    versions: list[ProposalVersion] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
class ExportDocxRequest(BaseModel):
    title: str
    context: ClientContext
    sections: list[SectionResult]
    proposal_id: Optional[str] = None


class ExportDocxResponse(BaseModel):
    filename: str
    download_url: str


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------
class KnowledgeBaseStatus(BaseModel):
    connected: bool
    collection: str
    points: int = 0
    mode: str = "local"
    embedding_ready: bool = False
    embedding_provider: str = ""
    embedding_model: str = ""
    message: str = ""


class GenericResponse(BaseModel):
    ok: bool = True
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseUploadResponse(BaseModel):
    files: list[str] = Field(default_factory=list)
    chunks_written: int = 0
    collection: str = ""
    detail: str = ""
