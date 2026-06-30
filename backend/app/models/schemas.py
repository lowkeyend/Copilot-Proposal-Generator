"""Pydantic schemas shared across the API surface.

These mirror the request/response contracts consumed by the Next.js
frontend. Keeping them in one place keeps the API self-documenting via
FastAPI's generated OpenAPI schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _uid() -> str:
    return uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Client context (Agent 1)
# --------------------------------------------------------------------------
class IntakeProfile(BaseModel):
    project_mode: Literal["implementation", "upgrade", "unknown"] = "implementation"
    upgrade_type: Literal["functional", "technical", "non-functional", "mixed", "unknown"] = "unknown"
    launch_segments: list[str] = Field(default_factory=list)
    module_list: list[str] = Field(default_factory=list)
    phase_1_products: list[str] = Field(default_factory=list)
    phase_2_products: list[str] = Field(default_factory=list)
    regulatory_interfaces_phase_1: list[str] = Field(default_factory=list)
    regulatory_interfaces_phase_2: list[str] = Field(default_factory=list)
    channels_phase_1: list[str] = Field(default_factory=list)
    channels_phase_2: list[str] = Field(default_factory=list)
    middleware_platform: str = ""
    reporting_platform: str = ""
    database_platform: str = ""
    hosting_model: str = ""
    container_platform: str = ""
    data_warehouse_platform: str = ""
    implementation_methodology: str = "TIM"
    delivery_model: str = "Phased MVP"
    current_system: str = ""
    current_version: str = ""
    target_version: str = ""
    upgrade_strategy: str = ""
    hardware_requirements: str = ""
    infrastructure_requirements: str = ""
    current_gaps: str = ""
    desired_capabilities: str = ""
    target_customers_year_1: str = ""
    target_customers_year_2: str = ""
    target_customers_year_3: str = ""
    target_accounts_year_1: str = ""
    target_accounts_year_2: str = ""
    target_accounts_year_3: str = ""
    launch_plan: str = ""
    questionnaire_notes: str = ""


class ClientContext(BaseModel):
    client_name: str = ""
    industry: str = ""
    project_type: str = ""
    client_profile: Literal["established", "greenfield", "unknown"] = "established"
    implementation_context: str = "Modernization / migration for an existing institution"
    canonical_product: str = "Temenos Transact"
    selected_documents: list[str] = Field(default_factory=list)
    intake: IntakeProfile = Field(default_factory=IntakeProfile)
    tone: str = "Formal"
    special_instructions: str = ""

    @field_validator("canonical_product", mode="before")
    @classmethod
    def _join_canonical_products(cls, value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip() or "Temenos Transact"


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
    selected_documents: list[str] = Field(default_factory=list)
    project_mode: Optional[Literal["implementation", "upgrade", "unknown"]] = None
    intake: Optional[IntakeProfile] = None


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
    source_document: str = ""
    proposal_family: str = ""
    chunk_id: str = ""
    source_type: str = "document"


class KnowledgeBaseChunk(BaseModel):
    chunk_id: str
    summary: str = ""
    text: str = ""
    source_proposal: str = ""
    source_section: str = ""
    source_document: str = ""
    proposal_family: str = ""
    score: float = 0.0
    payload: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseChunkUpdate(BaseModel):
    text: Optional[str] = None
    source_proposal: Optional[str] = None
    source_section: Optional[str] = None
    proposal_family: Optional[str] = None
    source_document: Optional[str] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class DocumentQueryRequest(BaseModel):
    question: str
    history: list[ChatMessage] = Field(default_factory=list)
    document_names: list[str] = Field(default_factory=list)
    model: Optional[str] = None
    top_k: int = 8


class DocumentQueryResponse(BaseModel):
    answer: str
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    used_documents: list[str] = Field(default_factory=list)


class ParsedField(BaseModel):
    key: str
    label: str
    value: str = ""
    category: str = ""
    confidence: float = 0.0
    source_excerpt: str = ""
    notes: str = ""


class RfpParseRequest(BaseModel):
    prompt: str = ""
    model: Optional[str] = None


class RfpParseResponse(BaseModel):
    filename: str = ""
    title: str = ""
    project_mode: Literal["implementation", "upgrade", "unknown"] = "unknown"
    storyline: str = ""
    fields: list[ParsedField] = Field(default_factory=list)
    intake: IntakeProfile = Field(default_factory=IntakeProfile)
    summary: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class PlannerRequest(BaseModel):
    context: ClientContext
    parsed_rfp: Optional[RfpParseResponse] = None
    model: Optional[str] = None


class PlannerResponse(BaseModel):
    next_steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    verifications: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    timeline_notes: list[str] = Field(default_factory=list)
    manday_estimates: list["MandayEstimate"] = Field(default_factory=list)
    role_assignments: list["RoleAssignment"] = Field(default_factory=list)
    decision_gates: list[str] = Field(default_factory=list)


class InsightItem(BaseModel):
    title: str
    detail: str
    severity: Literal["low", "medium", "high"] = "medium"
    evidence: list[str] = Field(default_factory=list)
    action: str = ""


class MandayEstimate(BaseModel):
    workstream: str
    low: int
    high: int
    rationale: str = ""


class RoleAssignment(BaseModel):
    role: str
    owns: list[str] = Field(default_factory=list)
    checkpoints: list[str] = Field(default_factory=list)


class ModuleHardwareClassification(BaseModel):
    module: str
    complexity: Literal["low", "medium", "high"] = "medium"
    hardware_band: Literal["small", "medium", "large"] = "medium"
    signals: list[str] = Field(default_factory=list)
    recommendation: str = ""


class InsightRequest(BaseModel):
    context: ClientContext
    parsed_rfp: Optional[RfpParseResponse] = None
    mode: Literal["agent", "web"] = "agent"
    focus_areas: list[str] = Field(default_factory=list)
    model: Optional[str] = None


class InsightResponse(BaseModel):
    summary: str = ""
    insight_items: list[InsightItem] = Field(default_factory=list)
    leakage_warnings: list[InsightItem] = Field(default_factory=list)
    scope_gaps: list[InsightItem] = Field(default_factory=list)
    manday_estimates: list[MandayEstimate] = Field(default_factory=list)
    role_assignments: list[RoleAssignment] = Field(default_factory=list)
    module_hardware: list[ModuleHardwareClassification] = Field(default_factory=list)
    proposal_targets: list[str] = Field(default_factory=list)
    next_best_actions: list[str] = Field(default_factory=list)


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


class OpenRouterSettingsUpdate(BaseModel):
    api_key: str = ""
    model: str = ""


class OpenRouterSettingsStatus(BaseModel):
    api_key_set: bool = False
    source: Literal["runtime", "env", "none"] = "none"
    default_model: str = "openrouter/free"
    models: list[str] = Field(default_factory=list)


class OpenRouterSettingsCheckResponse(BaseModel):
    ok: bool = False
    fallback: bool = True
    source: Literal["request", "runtime", "env", "none"] = "none"
    model: str = ""
    message: str = ""
    detail: str = ""


class GenericResponse(BaseModel):
    ok: bool = True
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseUploadResponse(BaseModel):
    files: list[str] = Field(default_factory=list)
    chunks_written: int = 0
    collection: str = ""
    detail: str = ""
