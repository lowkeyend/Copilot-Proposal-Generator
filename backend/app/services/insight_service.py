from __future__ import annotations

import re
from collections import OrderedDict

from app.models.schemas import (
    ClientContext,
    InsightItem,
    InsightResponse,
    MandayEstimate,
    ModuleHardwareClassification,
    RoleAssignment,
    RfpParseResponse,
)
from app.services.llm_service import LLMError, get_llm
from app.services.qdrant_service import get_qdrant


TECH_VISTA_BASELINE = {
    "phase_1_products": [
        "Savings Accounts",
        "Current Accounts",
        "Customer onboarding with KYC",
        "Domestic interbank payments",
        "ATM services",
        "AML screening and monitoring",
        "Internal bank transfers",
        "Teller Operation",
    ],
    "phase_2_products": [
        "International transfers",
        "Internet & Mobile Banking",
        "Retail & SME lending",
        "Corporate lending",
        "Trade finance",
        "Treasury products",
    ],
    "phase_1_interfaces": [
        "MMA regulatory reporting",
        "RTGS / ACH",
        "AML & sanctions screening",
        "ATM switch",
        "Identity verification",
    ],
    "phase_2_interfaces": ["Credit bureau", "Card schemes", "Government e-KYC"],
    "platform": ["Oracle Database 19c or higher", "AWS Cloud", "Temenos Reporting", "Temenos TDH"],
}


MODULE_PROFILE: dict[str, dict[str, object]] = {
    "core": {"band": "medium", "days": (55, 85), "signals": ["ledger", "accounts", "posting"]},
    "current": {"band": "medium", "days": (35, 55), "signals": ["accounts", "branch", "ledger"]},
    "savings": {"band": "medium", "days": (30, 50), "signals": ["accounts", "interest", "ledger"]},
    "onboarding": {"band": "medium", "days": (25, 45), "signals": ["kyc", "customer", "identity"]},
    "kyc": {"band": "medium", "days": (25, 45), "signals": ["identity", "screening", "workflow"]},
    "aml": {"band": "large", "days": (35, 65), "signals": ["screening", "sanctions", "regulatory"]},
    "payment": {"band": "large", "days": (45, 80), "signals": ["switch", "settlement", "regulatory rails"]},
    "rtgs": {"band": "large", "days": (35, 65), "signals": ["real-time settlement", "central bank", "cutover"]},
    "ach": {"band": "medium", "days": (25, 45), "signals": ["batch clearing", "payments", "reconciliation"]},
    "atm": {"band": "medium", "days": (25, 45), "signals": ["switch", "cards", "channel testing"]},
    "mobile": {"band": "large", "days": (45, 85), "signals": ["digital channel", "api load", "security"]},
    "internet": {"band": "large", "days": (40, 75), "signals": ["digital channel", "api load", "security"]},
    "lending": {"band": "large", "days": (50, 95), "signals": ["workflow", "collateral", "risk rules"]},
    "corporate": {"band": "large", "days": (45, 85), "signals": ["limits", "approvals", "relationship hierarchy"]},
    "trade": {"band": "large", "days": (55, 100), "signals": ["documents", "limits", "SWIFT"]},
    "treasury": {"band": "large", "days": (60, 110), "signals": ["markets", "limits", "settlement"]},
    "reporting": {"band": "medium", "days": (25, 50), "signals": ["MIS", "regulatory reports", "data quality"]},
    "tdh": {"band": "large", "days": (35, 70), "signals": ["warehouse", "analytics", "data pipeline"]},
}


def _unique(values: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys(item.strip() for item in values if item and item.strip()))


def _contains_any(value: str, terms: list[str]) -> bool:
    low = value.lower()
    return any(term.lower() in low for term in terms)


def _profile_for(module: str) -> dict[str, object]:
    low = module.lower()
    for key, profile in MODULE_PROFILE.items():
        if key in low:
            return profile
    return {"band": "small", "days": (12, 25), "signals": ["standard configuration"]}


def _collect_modules(context: ClientContext, parsed_rfp: RfpParseResponse | None) -> list[str]:
    intake = context.intake
    values = [
        *intake.module_list,
        *intake.phase_1_products,
        *intake.phase_2_products,
        *intake.regulatory_interfaces_phase_1,
        *intake.regulatory_interfaces_phase_2,
        *intake.channels_phase_1,
        *intake.channels_phase_2,
    ]
    if parsed_rfp:
        p = parsed_rfp.intake
        values.extend(
            [
                *p.module_list,
                *p.phase_1_products,
                *p.phase_2_products,
                *p.regulatory_interfaces_phase_1,
                *p.regulatory_interfaces_phase_2,
                *p.channels_phase_1,
                *p.channels_phase_2,
            ]
        )
    return _unique(values)


def _customer_scale_signal(context: ClientContext, parsed_rfp: RfpParseResponse | None) -> tuple[str, int]:
    text = " ".join(
        [
            context.intake.target_customers_year_1,
            context.intake.target_customers_year_2,
            context.intake.target_customers_year_3,
            context.intake.target_accounts_year_1,
            context.intake.target_accounts_year_2,
            context.intake.target_accounts_year_3,
            parsed_rfp.intake.target_customers_year_3 if parsed_rfp else "",
            parsed_rfp.intake.target_accounts_year_3 if parsed_rfp else "",
        ]
    )
    nums = [int(n.replace(",", "")) for n in re.findall(r"\b\d[\d,]{2,}\b", text)]
    peak = max(nums) if nums else 0
    if peak >= 100000:
        return "large projected customer or account volume", 2
    if peak >= 30000:
        return "medium projected customer or account volume", 1
    return "no high-volume projection detected", 0


def _module_hardware(modules: list[str], context: ClientContext, parsed_rfp: RfpParseResponse | None) -> list[ModuleHardwareClassification]:
    scale_signal, scale_boost = _customer_scale_signal(context, parsed_rfp)
    classifications: list[ModuleHardwareClassification] = []
    for module in modules[:40]:
        profile = _profile_for(module)
        band = str(profile["band"])
        signals = list(profile["signals"]) + [scale_signal]
        complexity_score = {"small": 1, "medium": 2, "large": 3}.get(band, 2) + scale_boost
        if complexity_score >= 4:
            complexity = "high"
            hardware_band = "large"
        elif complexity_score == 3:
            complexity = "medium"
            hardware_band = "medium"
        else:
            complexity = "low"
            hardware_band = "small"
        classifications.append(
            ModuleHardwareClassification(
                module=module,
                complexity=complexity,  # type: ignore[arg-type]
                hardware_band=hardware_band,  # type: ignore[arg-type]
                signals=_unique([str(signal) for signal in signals])[:4],
                recommendation=(
                    "Size with dedicated performance, resilience, and integration testing."
                    if hardware_band == "large"
                    else "Size as a standard configured workstream with shared platform capacity."
                ),
            )
        )
    return classifications


def _mandays(modules: list[str], context: ClientContext, parsed_rfp: RfpParseResponse | None) -> list[MandayEstimate]:
    totals = {
        "Functional configuration": [30, 45],
        "Integration and channels": [20, 35],
        "Data, reporting, and reconciliation": [18, 30],
        "Testing, training, and cutover": [25, 40],
        "Project governance and PMO": [15, 25],
    }
    for module in modules:
        profile = _profile_for(module)
        low, high = profile["days"]  # type: ignore[misc]
        target = "Functional configuration"
        if _contains_any(module, ["payment", "rtgs", "ach", "atm", "mobile", "internet", "swift", "api", "bureau", "kyc"]):
            target = "Integration and channels"
        if _contains_any(module, ["report", "tdh", "warehouse", "analytics", "data"]):
            target = "Data, reporting, and reconciliation"
        totals[target][0] += int(low) // 3
        totals[target][1] += int(high) // 3

    if context.intake.delivery_model == "Single Big Bang":
        totals["Testing, training, and cutover"][0] += 20
        totals["Testing, training, and cutover"][1] += 35
    if parsed_rfp and parsed_rfp.project_mode == "upgrade":
        totals["Data, reporting, and reconciliation"][0] += 25
        totals["Data, reporting, and reconciliation"][1] += 45

    return [
        MandayEstimate(
            workstream=name,
            low=values[0],
            high=values[1],
            rationale="Estimated from module count, integration scope, delivery model, and migration signals.",
        )
        for name, values in totals.items()
    ]


def _scope_gaps(context: ClientContext, parsed_rfp: RfpParseResponse | None) -> list[InsightItem]:
    intake = parsed_rfp.intake if parsed_rfp else context.intake
    gaps: list[InsightItem] = []
    required = [
        ("Phase 1 products", intake.phase_1_products),
        ("Regulatory interfaces", intake.regulatory_interfaces_phase_1),
        ("Channels", intake.channels_phase_1),
        ("Database platform", [intake.database_platform] if intake.database_platform else []),
        ("Hosting model", [intake.hosting_model] if intake.hosting_model else []),
        ("Launch plan", [intake.launch_plan] if intake.launch_plan else []),
    ]
    for label, values in required:
        if not values:
            gaps.append(
                InsightItem(
                    title=f"{label} missing",
                    detail=f"{label} should be confirmed before proposal generation.",
                    severity="high" if label in {"Phase 1 products", "Regulatory interfaces"} else "medium",
                    action=f"Add {label.lower()} to the questionnaire or parsed RFP fields.",
                )
            )
    return gaps


def _leakage_warnings(context: ClientContext, parsed_rfp: RfpParseResponse | None, modules: list[str]) -> list[InsightItem]:
    warnings: list[InsightItem] = []
    text = " ".join(
        [
            context.client_profile,
            context.intake.project_mode,
            parsed_rfp.project_mode if parsed_rfp else "",
            parsed_rfp.storyline if parsed_rfp else "",
            " ".join(field.value for field in parsed_rfp.fields[:80]) if parsed_rfp else "",
        ]
    ).lower()
    if context.client_profile == "established" and "greenfield" in text:
        warnings.append(
            InsightItem(
                title="Greenfield leakage risk",
                detail="The active context is established-bank modernization, but greenfield language appears in parsed material.",
                severity="high",
                evidence=["client_profile=established", "greenfield term detected"],
                action="Force the proposal prompt to exclude greenfield launch framing unless explicitly requested.",
            )
        )
    if context.intake.delivery_model == "Single Big Bang" and (_contains_any(" ".join(modules), ["mobile", "internet", "tdh", "treasury"]) or len(modules) > 10):
        warnings.append(
            InsightItem(
                title="Big Bang delivery risk",
                detail="The selected delivery model is big bang while scope includes high-dependency modules.",
                severity="high",
                evidence=modules[:6],
                action="Switch to phased MVP or explicitly justify big-bang cutover controls.",
            )
        )
    if parsed_rfp and parsed_rfp.project_mode == "upgrade" and not parsed_rfp.intake.current_version:
        warnings.append(
            InsightItem(
                title="Upgrade version gap",
                detail="The parser detects upgrade mode but no current version was mapped.",
                severity="medium",
                action="Confirm current release, target release, database version, and upgrade path.",
            )
        )
    return warnings


def _roles(modules: list[str], context: ClientContext) -> list[RoleAssignment]:
    roles = [
        RoleAssignment(
            role="Solution Architect",
            owns=["Target architecture", "integration boundaries", "non-functional assumptions"],
            checkpoints=["Architecture sign-off", "NFR validation", "environment readiness"],
        ),
        RoleAssignment(
            role="Functional Lead",
            owns=["Product scope", "configuration decisions", "fit-gap closure"],
            checkpoints=["Phase scope freeze", "configuration walkthrough", "UAT entry"],
        ),
        RoleAssignment(
            role="Integration Lead",
            owns=["Regulatory interfaces", "channels", "API middleware"],
            checkpoints=["Interface catalogue", "SIT readiness", "cutover rehearsal"],
        ),
        RoleAssignment(
            role="Data and Reporting Lead",
            owns=["Migration data", "reports", "reconciliation"],
            checkpoints=["Data mapping", "mock migration", "report sign-off"],
        ),
        RoleAssignment(
            role="PMO / Delivery Manager",
            owns=["TIM governance", "plan baseline", "RAID control"],
            checkpoints=["Steering cadence", "stage gate approvals", "proposal assumptions log"],
        ),
    ]
    if _contains_any(" ".join(modules), ["aml", "sanctions", "regulatory", "rtgs", "ach"]):
        roles.append(
            RoleAssignment(
                role="Compliance SME",
                owns=["Regulatory report interpretation", "AML controls", "audit evidence"],
                checkpoints=["Compliance walkthrough", "regulator-facing scope validation"],
            )
        )
    if context.intake.hosting_model or context.intake.container_platform:
        roles.append(
            RoleAssignment(
                role="Infrastructure Lead",
                owns=["AWS sizing", "database platform", "environment topology"],
                checkpoints=["Sizing baseline", "security controls", "DR readiness"],
            )
        )
    return roles


def _targets(context: ClientContext, parsed_rfp: RfpParseResponse | None, modules: list[str]) -> list[str]:
    intake = parsed_rfp.intake if parsed_rfp else context.intake
    targets = [
        f"Canonical product language: {context.canonical_product or 'Temenos Transact'}",
        f"Delivery model: {intake.delivery_model or context.intake.delivery_model or 'Phased MVP'}",
    ]
    if intake.phase_1_products:
        targets.append(f"Phase 1 scope: {', '.join(intake.phase_1_products[:8])}")
    if intake.regulatory_interfaces_phase_1:
        targets.append(f"Regulatory go-live dependencies: {', '.join(intake.regulatory_interfaces_phase_1[:6])}")
    if intake.launch_plan:
        targets.append(f"Launch plan: {intake.launch_plan}")
    if modules:
        targets.append(f"Module baseline: {', '.join(modules[:10])}")
    return targets


async def generate_insights(
    context: ClientContext,
    parsed_rfp: RfpParseResponse | None = None,
    mode: str = "agent",
    focus_areas: list[str] | None = None,
    model: str | None = None,
) -> InsightResponse:
    modules = _collect_modules(context, parsed_rfp)
    module_hardware = _module_hardware(modules, context, parsed_rfp)
    mandays = _mandays(modules, context, parsed_rfp)
    gaps = _scope_gaps(context, parsed_rfp)
    leakage = _leakage_warnings(context, parsed_rfp, modules)
    roles = _roles(modules, context)
    targets = _targets(context, parsed_rfp, modules)

    kb_hits = []
    try:
        query = " ".join([context.client_name, context.canonical_product, " ".join(modules[:10])]).strip()
        if query:
            kb_hits = get_qdrant().search_text(query, top_k=5)
    except Exception:
        kb_hits = []

    insight_items = [
        InsightItem(
            title="Evidence alignment",
            detail=f"{len(kb_hits)} high-signal knowledge chunks match the current scope.",
            severity="low" if kb_hits else "medium",
            evidence=[hit.summary or hit.source_document for hit in kb_hits[:3]],
            action="Use these chunks as the evidence set before generating final sections.",
        ),
        InsightItem(
            title="Module complexity shape",
            detail=f"{sum(1 for item in module_hardware if item.complexity == 'high')} high-complexity modules require early sizing and integration validation.",
            severity="high" if any(item.complexity == "high" for item in module_hardware) else "medium",
            evidence=[item.module for item in module_hardware if item.complexity == "high"][:5],
            action="Prioritize architecture, NFR, and SIT planning for high-complexity modules.",
        ),
    ]

    if mode == "web":
        insight_items.append(
            InsightItem(
                title="Web mode enabled",
                detail="Official vendor context may be used only where explicitly supported by source metadata.",
                severity="medium",
                action="Keep Temenos web material separate from client-specific RFP commitments.",
            )
        )

    summary = "Scope intelligence is ready."
    if modules:
        total_low = sum(item.low for item in mandays)
        total_high = sum(item.high for item in mandays)
        summary = f"{len(modules)} scoped items analyzed with an indicative {total_low}-{total_high} manday range."

    if get_llm().available:
        try:
            data = await get_llm().chat_json(
                [
                    {"role": "system", "content": "Return strict JSON for proposal insight synthesis."},
                    {
                        "role": "user",
                        "content": (
                            "Return JSON with summary and next_best_actions. Keep it grounded in this data only:\n"
                            f"context={context.model_dump_json()}\n"
                            f"parsed_rfp={parsed_rfp.model_dump_json() if parsed_rfp else '{}'}\n"
                            f"modules={modules[:25]}\n"
                            f"leakage={[item.model_dump() for item in leakage]}\n"
                            f"gaps={[item.model_dump() for item in gaps]}\n"
                        ),
                    },
                ],
                model=model,
                temperature=0.1,
                max_tokens=700,
            )
            if isinstance(data, dict):
                summary = str(data.get("summary") or summary).strip()
                next_best_actions = [str(item).strip() for item in data.get("next_best_actions", []) if str(item).strip()]
            else:
                next_best_actions = []
        except (LLMError, ValueError):
            next_best_actions = []
    else:
        next_best_actions = []

    if not next_best_actions:
        next_best_actions = [
            "Resolve all high-severity leakage warnings before section generation.",
            "Freeze Phase 1 products, regulatory interfaces, and launch plan.",
            "Use manday ranges to challenge timeline and resourcing assumptions.",
            "Map every high-complexity module to an owner and checkpoint.",
        ]

    return InsightResponse(
        summary=summary,
        insight_items=insight_items,
        leakage_warnings=leakage,
        scope_gaps=gaps,
        manday_estimates=mandays,
        role_assignments=roles,
        module_hardware=module_hardware,
        proposal_targets=targets,
        next_best_actions=next_best_actions[:8],
    )
