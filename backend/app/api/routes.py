"""HTTP API surface.

Thin orchestration over the agents + services. The route names match the
contract in the build spec; a few extra read/utility routes are added to
support the frontend (status, models, patterns, template CRUD, downloads).
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.models.schemas import (
    BuildTocRequest,
    BuildTocResponse,
    DocumentQueryRequest,
    DocumentQueryResponse,
    ExportDocxRequest,
    ExportDocxResponse,
    GenerateContextRequest,
    GenerateContextResponse,
    GenerateProposalRequest,
    GenerateProposalResponse,
    GenerateSectionRequest,
    GenericResponse,
    InsightRequest,
    InsightResponse,
    KnowledgeBaseStatus,
    OpenRouterSettingsStatus,
    OpenRouterSettingsCheckResponse,
    OpenRouterSettingsUpdate,
    KnowledgeBaseChunk,
    KnowledgeBaseUploadResponse,
    KnowledgeBaseChunkUpdate,
    PlannerRequest,
    PlannerResponse,
    ProposalRecord,
    ProposalTemplate,
    ProposalVersion,
    RfpParseResponse,
    ReviewProposalRequest,
    ReviewProposalResponse,
    SectionResult,
    SuggestTemplateRequest,
    SuggestTemplateResponse,
)

from app.agents.classifier_agent import run_classifier_agent
from app.agents.consistency_agent import run_consistency_agent
from app.agents.context_agent import run_context_agent
from app.agents.pattern_discovery import discover_patterns, load_registry
from app.agents.section_writer import run_section_writer
from app.agents.template_agent import run_template_agent
from app.agents.toc_agent import run_toc_agent

from app.services.document_query_service import answer_document_query
from app.services.docx_service import get_composer
from app.services.knowledge_ingest_service import get_knowledge_ingest
from app.services.llm_service import get_llm
from app.services.qdrant_service import get_qdrant
from app.services.planner_service import plan_next_steps
from app.services.runtime_settings_service import (
    get_openrouter_api_key,
    get_openrouter_key_source,
    save_runtime_settings,
)
from app.services.rfp_parser_service import parse_rfp_documents
from app.services.insight_service import generate_insights
from app.services.storage_service import get_storage

router = APIRouter()
settings = get_settings()


# --------------------------------------------------------------------------
# Meta / status
# --------------------------------------------------------------------------
@router.get("/status", response_model=KnowledgeBaseStatus, tags=["meta"])
def status() -> KnowledgeBaseStatus:
    return KnowledgeBaseStatus(**get_qdrant().status())


@router.get("/models", tags=["meta"])
def models() -> dict:
    return {
        "models": settings.supported_models,
        "default": settings.default_model,
        "llm_ready": get_llm().available,
    }


@router.get("/settings/llm", response_model=OpenRouterSettingsStatus, tags=["meta"])
def get_llm_settings() -> OpenRouterSettingsStatus:
    return OpenRouterSettingsStatus(
        api_key_set=bool(get_openrouter_api_key()),
        source=get_openrouter_key_source(),
        default_model=settings.default_model,
        models=settings.supported_models,
    )


@router.post("/settings/llm", response_model=OpenRouterSettingsStatus, tags=["meta"])
def update_llm_settings(req: OpenRouterSettingsUpdate) -> OpenRouterSettingsStatus:
    save_runtime_settings(req.api_key)
    return OpenRouterSettingsStatus(
        api_key_set=bool(get_openrouter_api_key()),
        source=get_openrouter_key_source(),
        default_model=settings.default_model,
        models=settings.supported_models,
    )


@router.post("/settings/llm/check", response_model=OpenRouterSettingsCheckResponse, tags=["meta"])
async def check_llm_settings(req: OpenRouterSettingsUpdate) -> OpenRouterSettingsCheckResponse:
    result = await get_llm().check(model=req.model or None, api_key=req.api_key or None)
    return OpenRouterSettingsCheckResponse(
        ok=bool(result.get("ok")),
        fallback=bool(result.get("fallback", True)),
        source="request" if (req.api_key or "").strip() else get_openrouter_key_source(),
        model=req.model or settings.default_model,
        message=str(result.get("message") or ""),
        detail=str(result.get("detail") or ""),
    )


@router.get("/knowledge-base/chunks", tags=["knowledge-base"])
def list_chunks(limit: int = 200) -> dict:
    chunks = get_qdrant().list_chunks(limit=limit)
    return {"chunks": [c.model_dump() for c in chunks], "count": len(chunks)}


@router.post("/knowledge-base/upload", response_model=KnowledgeBaseUploadResponse, tags=["knowledge-base"])
async def upload_chunks(
    files: list[UploadFile] = File(...),
    source_proposal: str = Form(""),
    source_section: str = Form(""),
    proposal_family: str = Form("Uploaded Knowledge"),
) -> KnowledgeBaseUploadResponse:
    try:
        filenames, count = await get_knowledge_ingest().ingest_files(
            files=files,
            source_proposal=source_proposal.strip(),
            source_section=source_section.strip(),
            proposal_family=proposal_family.strip(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KnowledgeBaseUploadResponse(
        files=filenames,
        chunks_written=count,
        collection=settings.qdrant_collection,
        detail="Uploaded files were chunked and written to the active Qdrant collection.",
    )


@router.patch("/knowledge-base/chunks/{chunk_id}", response_model=KnowledgeBaseChunk, tags=["knowledge-base"])
def update_chunk(chunk_id: str, req: KnowledgeBaseChunkUpdate) -> KnowledgeBaseChunk:
    payload = {
        k: v
        for k, v in req.model_dump(exclude_none=True).items()
        if v is not None and v != ""
    }
    updated = get_qdrant().update_chunk(chunk_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Chunk not found or update failed.")
    return updated


@router.delete("/knowledge-base/chunks/{chunk_id}", response_model=GenericResponse, tags=["knowledge-base"])
def delete_chunk(chunk_id: str) -> GenericResponse:
    ok = get_qdrant().delete_chunk(chunk_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chunk not found or delete failed.")
    return GenericResponse(ok=True, detail="deleted")


@router.post("/query-docs", response_model=DocumentQueryResponse, tags=["knowledge-base"])
async def query_docs(req: DocumentQueryRequest) -> DocumentQueryResponse:
    return await answer_document_query(
        question=req.question,
        history=req.history,
        document_names=req.document_names,
        model=req.model,
        top_k=req.top_k,
    )


@router.post("/parse-rfp", response_model=RfpParseResponse, tags=["knowledge-base"])
async def parse_rfp(
    files: list[UploadFile] = File(...),
    model: str = Form(""),
) -> RfpParseResponse:
    try:
        return await parse_rfp_documents(files, model=model or None)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plan-next-steps", response_model=PlannerResponse, tags=["agents"])
async def plan_next_steps_route(req: PlannerRequest) -> PlannerResponse:
    return await plan_next_steps(req.context, req.parsed_rfp, req.model)


@router.post("/insight-studio/analyze", response_model=InsightResponse, tags=["agents"])
async def insight_studio(req: InsightRequest) -> InsightResponse:
    return await generate_insights(
        context=req.context,
        parsed_rfp=req.parsed_rfp,
        mode=req.mode,
        focus_areas=req.focus_areas,
        model=req.model,
    )


# --------------------------------------------------------------------------
# Agent 1 + 2 — context & classification
# --------------------------------------------------------------------------
@router.post("/generate-context", response_model=GenerateContextResponse, tags=["agents"])
async def generate_context(req: GenerateContextRequest) -> GenerateContextResponse:
    context = await run_context_agent(req)
    family, confidence, rationale = await run_classifier_agent(
        req.prompt, context, req.model
    )
    return GenerateContextResponse(
        context=context,
        proposal_family=family,
        family_confidence=confidence,
        family_rationale=rationale,
    )


# --------------------------------------------------------------------------
# Agent 3 — pattern discovery
# --------------------------------------------------------------------------
@router.get("/patterns", tags=["agents"])
def get_patterns() -> dict:
    patterns = load_registry()
    return {"patterns": [p.model_dump() for p in patterns]}


@router.post("/discover-patterns", tags=["agents"])
def rediscover_patterns() -> dict:
    patterns = discover_patterns()
    return {
        "count": len(patterns),
        "patterns": [p.model_dump() for p in patterns],
    }


# --------------------------------------------------------------------------
# Agent 4 — template suggestion
# --------------------------------------------------------------------------
@router.post("/suggest-template", response_model=SuggestTemplateResponse, tags=["agents"])
def suggest_template(req: SuggestTemplateRequest) -> SuggestTemplateResponse:
    return run_template_agent(req)


# --------------------------------------------------------------------------
# Agent 5 — TOC builder
# --------------------------------------------------------------------------
@router.post("/build-toc", response_model=BuildTocResponse, tags=["agents"])
async def build_toc(req: BuildTocRequest) -> BuildTocResponse:
    toc = await run_toc_agent(req)
    return BuildTocResponse(toc=toc)


# --------------------------------------------------------------------------
# Agents 6 + 7 — single section generation / regeneration
# --------------------------------------------------------------------------
@router.post("/generate-section", response_model=SectionResult, tags=["agents"])
async def generate_section(req: GenerateSectionRequest) -> SectionResult:
    return await run_section_writer(req)


@router.post("/regenerate-section", response_model=SectionResult, tags=["agents"])
async def regenerate_section(req: GenerateSectionRequest) -> SectionResult:
    # Same machinery; the UI passes an `instruction` for targeted rewrites.
    return await run_section_writer(req)


# --------------------------------------------------------------------------
# Full proposal generation (section-by-section orchestration)
# --------------------------------------------------------------------------
@router.post("/generate-proposal", response_model=GenerateProposalResponse, tags=["agents"])
async def generate_proposal(req: GenerateProposalRequest) -> GenerateProposalResponse:
    if not req.toc:
        raise HTTPException(status_code=400, detail="TOC is empty; build a TOC first.")

    storage = get_storage()
    title = (
        f"{req.context.project_type} Proposal for {req.context.client_name}".strip()
        if req.context.client_name
        else (req.context.project_type or "Proposal")
    )

    record = ProposalRecord(
        title=title,
        prompt=req.prompt,
        context=req.context,
        proposal_family=req.proposal_family,
        toc=req.toc,
    )

    sections: list[SectionResult] = []
    for toc_item in req.toc:
        section_req = GenerateSectionRequest(
            section_title=toc_item.title,
            keywords=toc_item.keywords,
            context=req.context,
            proposal_family=req.proposal_family,
            prompt=req.prompt,
            pattern_guidance=toc_item.description,
            model=req.model,
            top_k=req.top_k,
            include_temenos_official=req.include_temenos_official,
            use_hybrid_retrieval=req.use_hybrid_retrieval,
            detail_level=req.detail_level,
            require_evidence=req.require_evidence,
        )
        result = await run_section_writer(section_req)
        # Preserve the TOC id so the frontend can map sections <-> outline.
        result.id = toc_item.id
        sections.append(result)

    record = storage.save_proposal(record)
    version = storage.add_version(record.proposal_id, sections, label="Initial draft")

    return GenerateProposalResponse(
        proposal_id=record.proposal_id,
        version_id=version.version_id if version else "",
        sections=sections,
    )


# --------------------------------------------------------------------------
# Agent 8 — consistency review
# --------------------------------------------------------------------------
@router.post("/proposals/persist", response_model=GenerateProposalResponse, tags=["proposals"])
def persist_proposal(req: GenerateProposalRequest, sections: list[SectionResult]) -> GenerateProposalResponse:
    """Persist sections generated section-by-section by the frontend.

    Lets the UI show live per-section progress (calling /generate-section in a
    loop) while still creating a saved ProposalRecord + initial version.
    """
    storage = get_storage()
    title = (
        f"{req.context.project_type} Proposal for {req.context.client_name}".strip()
        if req.context.client_name
        else (req.context.project_type or "Proposal")
    )
    record = ProposalRecord(
        title=title,
        prompt=req.prompt,
        context=req.context,
        proposal_family=req.proposal_family,
        toc=req.toc,
    )
    record = storage.save_proposal(record)
    version = storage.add_version(record.proposal_id, sections, label="Initial draft")
    return GenerateProposalResponse(
        proposal_id=record.proposal_id,
        version_id=version.version_id if version else "",
        sections=sections,
    )


@router.post("/review-proposal", response_model=ReviewProposalResponse, tags=["agents"])
async def review_proposal(req: ReviewProposalRequest) -> ReviewProposalResponse:
    return await run_consistency_agent(req)


# --------------------------------------------------------------------------
# Agent 9 — DOCX export
# --------------------------------------------------------------------------
@router.post("/export-docx", response_model=ExportDocxResponse, tags=["agents"])
def export_docx(req: ExportDocxRequest) -> ExportDocxResponse:
    if not req.sections:
        raise HTTPException(status_code=400, detail="No sections to export.")
    path = get_composer().compose(
        title=req.title,
        context=req.context,
        sections=req.sections,
        proposal_id=req.proposal_id,
    )
    # Snapshot a version if this export is tied to a saved proposal.
    if req.proposal_id:
        get_storage().add_version(req.proposal_id, req.sections, label="Exported")
    return ExportDocxResponse(
        filename=path.name,
        download_url=f"/files/{path.name}",
    )


@router.get("/download/{filename}", tags=["agents"])
def download(filename: str) -> FileResponse:
    path = settings.generated_path / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


# --------------------------------------------------------------------------
# Templates CRUD
# --------------------------------------------------------------------------
@router.get("/templates", tags=["templates"])
def list_templates() -> dict:
    storage = get_storage()
    user_templates = storage.load_templates()
    discovered = load_registry()
    return {
        "user": [t.model_dump() for t in user_templates],
        "discovered": [t.model_dump() for t in discovered],
    }


@router.post("/templates", response_model=ProposalTemplate, tags=["templates"])
def upsert_template(template: ProposalTemplate) -> ProposalTemplate:
    template.origin = "user"
    return get_storage().upsert_template(template)


@router.delete("/templates/{template_id}", response_model=GenericResponse, tags=["templates"])
def delete_template(template_id: str) -> GenericResponse:
    ok = get_storage().delete_template(template_id)
    return GenericResponse(ok=ok, detail="deleted" if ok else "not found")


# --------------------------------------------------------------------------
# Proposals & versions
# --------------------------------------------------------------------------
@router.get("/proposals", tags=["proposals"])
def list_proposals() -> dict:
    return {
        "proposals": [
            {
                "proposal_id": r.proposal_id,
                "title": r.title,
                "proposal_family": r.proposal_family,
                "updated_at": r.updated_at,
                "versions": len(r.versions),
            }
            for r in get_storage().list_proposals()
        ]
    }


@router.get("/proposals/{proposal_id}", response_model=ProposalRecord, tags=["proposals"])
def get_proposal(proposal_id: str) -> ProposalRecord:
    record = get_storage().get_proposal(proposal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return record


@router.get("/versions", tags=["proposals"])
def list_versions(proposal_id: str) -> dict:
    record = get_storage().get_proposal(proposal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return {
        "proposal_id": proposal_id,
        "versions": [
            {
                "version_id": v.version_id,
                "label": v.label,
                "created_at": v.created_at,
                "sections": len(v.sections),
            }
            for v in record.versions
        ],
    }


@router.get("/versions/{proposal_id}/{version_id}", response_model=ProposalVersion, tags=["proposals"])
def get_version(proposal_id: str, version_id: str) -> ProposalVersion:
    version = get_storage().restore_version(proposal_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    return version


@router.post("/versions/{proposal_id}/{version_id}/duplicate", response_model=ProposalVersion, tags=["proposals"])
def duplicate_version(proposal_id: str, version_id: str) -> ProposalVersion:
    version = get_storage().duplicate_version(proposal_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    return version


@router.post("/proposals/{proposal_id}/save-version", response_model=ProposalVersion, tags=["proposals"])
def save_version(proposal_id: str, sections: list[SectionResult], label: str = "") -> ProposalVersion:
    version = get_storage().add_version(proposal_id, sections, label=label)
    if version is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return version
