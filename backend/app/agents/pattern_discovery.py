"""Agent 3 — Pattern Discovery Agent (CRITICAL).

Patterns are NOT hardcoded. They are learned from the existing proposal
corpus stored in Qdrant:

  1. Scroll all chunk payloads.
  2. Group chunks into (family, source_proposal) -> ordered section list.
  3. For each family, find sections that recur across its proposals and order
     them by their typical position. That ordered, recurring skeleton *is*
     the discovered pattern/template for the family.
  4. Persist the result to ../storage/pattern_registry.json.

Re-running discovery after more proposals are ingested automatically updates
the registry (the API exposes POST /discover-patterns).

When the corpus is empty (e.g. fresh clone before the Qdrant DB is attached)
we fall back to a small set of seed skeletons so the rest of the platform is
demonstrable. Seeds are clearly marked with support=0.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from app.config import get_settings
from app.models.schemas import ProposalTemplate, TemplateSection
from app.services.qdrant_service import get_qdrant


def _registry_path() -> Path:
    return get_settings().storage_path / "pattern_registry.json"


# --------------------------------------------------------------------------
# Section-title normalisation: collapse "1. Executive Summary" / "EXEC SUMMARY"
# heading variants into a canonical, comparable label.
# --------------------------------------------------------------------------
_CANONICAL = {
    "executive summary": "Executive Summary",
    "introduction": "Introduction",
    "overview": "Solution Overview",
    "solution overview": "Solution Overview",
    "scope": "Scope of Work",
    "scope of work": "Scope of Work",
    "approach": "Approach & Methodology",
    "methodology": "Approach & Methodology",
    "architecture": "Solution Architecture",
    "solution architecture": "Solution Architecture",
    "migration": "Migration Strategy",
    "data migration": "Migration Strategy",
    "security": "Security & Compliance",
    "compliance": "Security & Compliance",
    "testing": "Testing & Quality Assurance",
    "qa": "Testing & Quality Assurance",
    "training": "Training & Enablement",
    "timeline": "Project Timeline",
    "project plan": "Project Timeline",
    "implementation plan": "Project Timeline",
    "governance": "Governance & Project Management",
    "project management": "Governance & Project Management",
    "team": "Team & Resourcing",
    "resourcing": "Team & Resourcing",
    "pricing": "Commercials & Pricing",
    "commercials": "Commercials & Pricing",
    "cost": "Commercials & Pricing",
    "support": "Support & Maintenance",
    "maintenance": "Support & Maintenance",
    "risk": "Risk Management",
    "assumptions": "Assumptions & Dependencies",
    "conclusion": "Conclusion",
    "next steps": "Next Steps",
    "about": "About Us",
    "company": "About Us",
}


def _canonical_section(raw: str) -> str:
    if not raw:
        return ""
    # take the deepest heading level if a path like "A > B > C" was stored
    leaf = raw.split(">")[-1]
    cleaned = re.sub(r"^[\s\d.)\-]+", "", leaf).strip()
    low = cleaned.lower()
    for needle, canon in _CANONICAL.items():
        if needle in low:
            return canon
    # Title-case fallback, keep short labels only.
    if 0 < len(cleaned) <= 60:
        return cleaned.title()
    return ""


def _keywords_for(section_title: str) -> list[str]:
    base = re.sub(r"[^a-z ]", "", section_title.lower())
    words = [w for w in base.split() if len(w) > 2 and w not in {"and", "the"}]
    return words[:6] or [section_title.lower()]


# --------------------------------------------------------------------------
def discover_patterns(min_support_ratio: float = 0.34) -> list[ProposalTemplate]:
    """Learn patterns from Qdrant and persist them. Returns the registry."""
    qdrant = get_qdrant()
    payloads = qdrant.scroll_payloads()

    if not payloads:
        templates = _seed_patterns()
        _save_registry(templates)
        return templates

    # (family, source) -> ordered list of canonical section titles (deduped, kept in order)
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for payload in payloads:
        norm = qdrant.normalize_payload(payload)
        family = norm["family"] or "General"
        source = norm["source"] or "unknown"
        section = _canonical_section(norm["section"])
        if not section:
            continue
        bucket = grouped[(family, source)]
        if section not in bucket:
            bucket.append(section)

    # family -> list of per-proposal section lists
    by_family: dict[str, list[list[str]]] = defaultdict(list)
    for (family, _source), sections in grouped.items():
        if sections:
            by_family[family].append(sections)

    templates: list[ProposalTemplate] = []
    for family, proposals in by_family.items():
        support = len(proposals)
        freq: Counter[str] = Counter()
        positions: dict[str, list[float]] = defaultdict(list)
        for sections in proposals:
            n = len(sections)
            for idx, sec in enumerate(sections):
                freq[sec] += 1
                positions[sec].append(idx / max(1, n - 1) if n > 1 else 0.0)

        threshold = max(1, round(support * min_support_ratio))
        chosen = [sec for sec, count in freq.items() if count >= threshold]
        if not chosen:  # very small family: keep the most common handful
            chosen = [sec for sec, _ in freq.most_common(6)]
        chosen.sort(key=lambda s: median(positions[s]))

        templates.append(
            ProposalTemplate(
                name=f"{family} — discovered pattern",
                proposal_family=family,
                origin="discovered",
                support=support,
                sections=[
                    TemplateSection(
                        title=sec,
                        keywords=_keywords_for(sec),
                        description=f"Appears in {freq[sec]}/{support} {family} proposals.",
                    )
                    for sec in chosen
                ],
            )
        )

    templates.sort(key=lambda t: t.support, reverse=True)
    if not templates:
        templates = _seed_patterns()
    _save_registry(templates)
    return templates


# --------------------------------------------------------------------------
def load_registry() -> list[ProposalTemplate]:
    path = _registry_path()
    if not path.exists():
        return _merge_curated(discover_patterns())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _merge_curated([ProposalTemplate.model_validate(t) for t in raw.get("patterns", [])])
    except Exception:
        return _merge_curated(discover_patterns())


def _save_registry(templates: list[ProposalTemplate]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(templates),
                "patterns": [t.model_dump() for t in templates],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def known_families() -> list[str]:
    return sorted({t.proposal_family for t in load_registry() if t.proposal_family})


def pattern_for_family(family: str) -> ProposalTemplate | None:
    registry = load_registry()
    exact = [t for t in registry if t.proposal_family.lower() == family.lower()]
    if exact:
        return max(exact, key=lambda t: t.support)
    # fuzzy contains
    for t in registry:
        if family.lower() in t.proposal_family.lower() or (
            t.proposal_family.lower() in family.lower() and t.proposal_family
        ):
            return t
    return None


# --------------------------------------------------------------------------
def _seed_patterns() -> list[ProposalTemplate]:
    """Fallback skeletons used only when the corpus is empty."""
    seeds: dict[str, list[str]] = {
        "Temenos": [
            "Executive Summary",
            "Solution Overview",
            "Solution Architecture",
            "Migration Strategy",
            "Security & Compliance",
            "Testing & Quality Assurance",
            "Training & Enablement",
            "Project Timeline",
            "Commercials & Pricing",
        ],
        "Cloud Migration": [
            "Executive Summary",
            "Current State Assessment",
            "Target Architecture",
            "Migration Strategy",
            "Security & Compliance",
            "Project Timeline",
            "Commercials & Pricing",
        ],
        "Cybersecurity": [
            "Executive Summary",
            "Threat Landscape",
            "Approach & Methodology",
            "Security & Compliance",
            "Governance & Project Management",
            "Project Timeline",
            "Commercials & Pricing",
        ],
        "Managed Services": [
            "Executive Summary",
            "Scope of Work",
            "Service Levels",
            "Support & Maintenance",
            "Governance & Project Management",
            "Commercials & Pricing",
        ],
    }
    out: list[ProposalTemplate] = []
    for family, sections in seeds.items():
        out.append(
            ProposalTemplate(
                name=f"{family} — seed pattern",
                proposal_family=family,
                origin="discovered",
                support=0,
                sections=[
                    TemplateSection(
                        title=s,
                        keywords=_keywords_for(s),
                        description="Seed skeleton (no corpus attached yet).",
                    )
                    for s in sections
                ],
            )
        )
    return out


def _curated_patterns() -> list[ProposalTemplate]:
    return [
        ProposalTemplate(
            name="Temenos — greenfield MVP launch",
            proposal_family="Temenos",
            origin="discovered",
            support=0,
            sections=[
                TemplateSection(title="Executive Summary", keywords=["summary", "objective"], description="State the launch intent and business outcome."),
                TemplateSection(title="Client Objectives & Launch Scope", keywords=["segments", "mvp", "launch"], description="Capture the intended market segments and launch scope."),
                TemplateSection(title="Product Scope by Phase", keywords=["products", "phase"], description="Break products into phase 1 and phase 2."),
                TemplateSection(title="Integration & Interface Scope", keywords=["interfaces", "channels"], description="List regulatory, digital, and internal interfaces."),
                TemplateSection(title="Architecture & Hosting", keywords=["cloud", "database", "container"], description="Describe target hosting and environment."),
                TemplateSection(title="TIM Delivery Approach", keywords=["tim", "methodology"], description="Explain the TIM delivery phases and governance."),
                TemplateSection(title="Testing, Cutover & Go-Live", keywords=["testing", "cutover"], description="Describe readiness, validation, and rollout."),
                TemplateSection(title="Training & Handover", keywords=["training", "change"], description="Describe enablement and ownership transfer."),
                TemplateSection(title="Timeline & Milestones", keywords=["timeline", "milestones"], description="Outline the MVP schedule."),
            ],
        ),
        ProposalTemplate(
            name="Temenos — established bank modernization",
            proposal_family="Temenos",
            origin="discovered",
            support=0,
            sections=[
                TemplateSection(title="Executive Summary", keywords=["summary", "objective"], description="Frame the modernization case."),
                TemplateSection(title="Current State & Objectives", keywords=["current state", "objectives"], description="Summarize the existing environment and goals."),
                TemplateSection(title="Solution Scope & Product Coverage", keywords=["scope", "products"], description="Describe the target product set."),
                TemplateSection(title="Data Migration & Validation", keywords=["migration", "validation"], description="Cover data, reconciliation, and cutover."),
                TemplateSection(title="Security, Compliance & Controls", keywords=["security", "compliance"], description="Align controls to the migration plan."),
                TemplateSection(title="Integration & Channels", keywords=["integration", "channels"], description="Cover existing and new channels."),
                TemplateSection(title="TIM Delivery Approach", keywords=["tim", "methodology"], description="Explain process-led delivery and governance."),
                TemplateSection(title="Testing, Cutover & Stabilization", keywords=["testing", "cutover"], description="Detail SIT, UAT, go-live, and hypercare."),
                TemplateSection(title="Project Governance & Timeline", keywords=["governance", "timeline"], description="Set the cadence and milestones."),
            ],
        ),
        ProposalTemplate(
            name="Core Banking RFP response",
            proposal_family="Core Banking",
            origin="discovered",
            support=0,
            sections=[
                TemplateSection(title="Executive Summary", keywords=["summary", "objective"], description="Restate the RFP ask."),
                TemplateSection(title="Functional Scope", keywords=["functional", "scope"], description="Capture the functional requirements."),
                TemplateSection(title="Technical Scope", keywords=["technical", "hosting", "database"], description="Capture infrastructure and technical requirements."),
                TemplateSection(title="Integrations & Reporting", keywords=["integration", "reporting"], description="Map interfaces and reporting."),
                TemplateSection(title="Implementation Methodology", keywords=["implementation", "tim"], description="Describe delivery approach."),
                TemplateSection(title="Assumptions & Dependencies", keywords=["assumptions", "dependencies"], description="State scope assumptions clearly."),
                TemplateSection(title="Evaluation & Compliance Notes", keywords=["evaluation", "compliance"], description="Align response to the RFP evaluation."),
            ],
        ),
        ProposalTemplate(
            name="Digital wallet / omnichannel banking",
            proposal_family="Digital Wallet",
            origin="discovered",
            support=0,
            sections=[
                TemplateSection(title="Executive Summary", keywords=["summary", "objective"], description="Frame the wallet business case."),
                TemplateSection(title="Wallet Scope & User Journeys", keywords=["wallet", "journeys"], description="Describe channels and end-user journeys."),
                TemplateSection(title="API & Integration Layer", keywords=["api", "integration"], description="Cover the interface layer."),
                TemplateSection(title="Core Services & Backend", keywords=["backend", "services"], description="Describe wallet services and core dependencies."),
                TemplateSection(title="Security & Fraud Controls", keywords=["security", "fraud"], description="Explain protection and controls."),
                TemplateSection(title="Testing & Go-Live", keywords=["testing", "go-live"], description="Explain test and rollout approach."),
            ],
        ),
    ]


def _merge_curated(patterns: list[ProposalTemplate]) -> list[ProposalTemplate]:
    curated = _curated_patterns()
    seen = {(t.name.lower(), t.proposal_family.lower()) for t in patterns}
    merged = list(patterns)
    for template in curated:
        key = (template.name.lower(), template.proposal_family.lower())
        if key not in seen:
            merged.append(template)
    merged.sort(key=lambda t: (t.support, t.proposal_family), reverse=True)
    return merged
