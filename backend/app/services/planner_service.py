from __future__ import annotations

from app.models.schemas import PlannerResponse, RfpParseResponse
from app.services.llm_service import LLMError, get_llm
from app.services.insight_service import generate_insights


async def plan_next_steps(
    context,
    parsed_rfp: RfpParseResponse | None = None,
    model: str | None = None,
) -> PlannerResponse:
    next_steps: list[str] = []
    risks: list[str] = []
    verifications: list[str] = []
    milestones: list[str] = []
    open_questions: list[str] = []
    timeline_notes: list[str] = []
    manday_estimates = []
    role_assignments = []
    decision_gates: list[str] = []
    selected_documents = [
        doc.strip()
        for doc in getattr(context, "selected_documents", []) or []
        if str(doc).strip()
    ]
    intake = getattr(context, "intake", None)
    project_mode = getattr(intake, "project_mode", "unknown") if intake else "unknown"
    upgrade_type = getattr(intake, "upgrade_type", "unknown") if intake else "unknown"

    try:
        insights = await generate_insights(context, parsed_rfp, mode="agent", model=model)
        manday_estimates = insights.manday_estimates
        role_assignments = insights.role_assignments
        if insights.leakage_warnings:
            risks.extend(f"{item.title}: {item.detail}" for item in insights.leakage_warnings[:4])
        if insights.scope_gaps:
            verifications.extend(f"{item.title}: {item.action}" for item in insights.scope_gaps[:4])
        decision_gates.extend(
            [
                "Scope freeze gate: phase products, integrations, and exclusions signed off.",
                "Architecture gate: hosting, database, NFR, and security assumptions signed off.",
                "Evidence gate: all proposal claims mapped to retrieved KB or parsed RFP fields.",
                "Commercial gate: manday ranges and role ownership reviewed before submission.",
            ]
        )
    except Exception:
        pass

    if selected_documents:
        next_steps.append(
            f"Restrict proposal drafting to the selected reference documents: {', '.join(selected_documents[:6])}."
        )
        verifications.append(
            f"Confirm every proposal claim is supported by one of the {len(selected_documents)} selected reference documents."
        )
        decision_gates.append("Reference scope gate: only selected KB documents are allowed as source evidence.")

    if project_mode == "upgrade":
        if upgrade_type == "functional":
            next_steps.append("Focus the plan on functional changes, business process mapping, and module-by-module scope confirmation.")
            risks.append("Functional upgrade scope can drift if module boundaries are not frozen early.")
        elif upgrade_type == "technical":
            next_steps.append("Focus the plan on platform, version, infrastructure, and cutover dependencies.")
            risks.append("Technical upgrade scope can drift if the current version and target version are not validated early.")
        elif upgrade_type == "non-functional":
            next_steps.append("Focus the plan on performance, resilience, security, and capacity requirements.")
            risks.append("Non-functional upgrade scope can be underestimated if NFRs are not made explicit.")
        elif upgrade_type == "mixed":
            next_steps.append("Split the plan into functional, technical, and non-functional workstreams before the draft is frozen.")
            risks.append("Mixed upgrade scope can become inconsistent if the three workstream types are not separated.")
        if getattr(intake, "current_system", "") or getattr(intake, "current_version", ""):
            verifications.append(
                f"Validate the upgrade baseline: {getattr(intake, 'current_system', '') or 'current system'} {getattr(intake, 'current_version', '') or ''}".strip()
            )
        if getattr(intake, "target_version", ""):
            verifications.append(f"Validate the target version and upgrade path to {intake.target_version}.")
    elif project_mode == "implementation":
        next_steps.append("Treat the proposal as an implementation launch and keep migration assumptions out unless explicitly supported.")
        decision_gates.append("Implementation gate: launch scope, delivery model, and phase sequencing are agreed before drafting.")

    if parsed_rfp:
        next_steps.extend(parsed_rfp.next_steps[:5])
        if parsed_rfp.missing_fields:
            verifications.extend(f"Confirm {item}" for item in parsed_rfp.missing_fields[:5])
        if parsed_rfp.intake.current_system and parsed_rfp.intake.target_version:
            next_steps.append(
                f"Validate the upgrade path from {parsed_rfp.intake.current_system} to {parsed_rfp.intake.target_version}."
            )
        if parsed_rfp.intake.phase_1_products:
            next_steps.append(
                f"Confirm Phase 1 scope for {', '.join(parsed_rfp.intake.phase_1_products[:5])} before any Phase 2 commitments."
            )
        if parsed_rfp.intake.phase_2_products:
            next_steps.append(
                f"Plan Phase 2 only after Phase 1 acceptance for {', '.join(parsed_rfp.intake.phase_2_products[:5])}."
            )
        if parsed_rfp.intake.launch_plan:
            verifications.append(f"Validate launch sequencing: {parsed_rfp.intake.launch_plan}")
        if parsed_rfp.intake.module_list:
            milestones.append(
                f"Confirm the module baseline across {', '.join(parsed_rfp.intake.module_list[:6])} before proposal lock."
            )
            timeline_notes.append(
                "Use the module list as the backbone for the delivery timeline and workstream mapping."
            )
        if parsed_rfp.intake.current_system or parsed_rfp.intake.target_version:
            open_questions.append(
                f"Confirm the exact current platform and target version for the {parsed_rfp.intake.current_system or 'upgrade'} path."
            )
        if parsed_rfp.storyline:
            milestones.append("Align the proposal storyline to the parsed storyline before drafting execution text.")

    if getattr(context, "client_profile", "") == "greenfield":
        risks.append("Greenfield scope must not inherit migration assumptions from established-bank evidence.")
    if getattr(context, "client_profile", "") == "established":
        risks.append("Established-bank modernization requires explicit cutover, validation, and security mapping.")

    if intake:
        if intake.phase_2_products and not intake.phase_1_products:
            verifications.append("Confirm which phase-1 products must be available before phase-2 scope begins.")
        if intake.delivery_model == "Single Big Bang":
            risks.append("Single big-bang delivery increases cutover and data migration risk.")
        if intake.module_list:
            open_questions.append("Validate whether any selected modules should be deferred to a later phase.")
            timeline_notes.append("Each module should map to a stage gate, owner, and evidence set.")
        if intake.upgrade_type == "functional":
            timeline_notes.append("Functional upgrade planning should track business design, process change, and user impact.")
        elif intake.upgrade_type == "technical":
            timeline_notes.append("Technical upgrade planning should track platform readiness, cutover, and regression testing.")
        elif intake.upgrade_type == "non-functional":
            timeline_notes.append("Non-functional upgrade planning should track performance, security, capacity, and resilience checkpoints.")

    prompt = f"""You are a proposal planning agent.
Return STRICT JSON:
{{
  "next_steps": ["..."],
  "risks": ["..."],
  "verifications": ["..."],
  "milestones": ["..."],
  "open_questions": ["..."],
  "timeline_notes": ["..."],
  "decision_gates": ["..."]
}}

CLIENT CONTEXT:
{context.model_dump_json(indent=2)}

RFP SUMMARY:
{parsed_rfp.model_dump_json(indent=2) if parsed_rfp else "{}"}

Use concise, actionable planning language.
If selected_documents is present in CLIENT CONTEXT, prioritize those documents and do not broaden scope to the full KB."""

    try:
        data = await get_llm().chat_json(
            [
                {"role": "system", "content": "You are a strict JSON planning engine."},
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0.15,
            max_tokens=1000,
        )
        next_steps = [str(item).strip() for item in data.get("next_steps", []) if str(item).strip()] or next_steps
        risks = [str(item).strip() for item in data.get("risks", []) if str(item).strip()] or risks
        verifications = [str(item).strip() for item in data.get("verifications", []) if str(item).strip()] or verifications
        milestones = [str(item).strip() for item in data.get("milestones", []) if str(item).strip()] or milestones
        open_questions = [str(item).strip() for item in data.get("open_questions", []) if str(item).strip()] or open_questions
        timeline_notes = [str(item).strip() for item in data.get("timeline_notes", []) if str(item).strip()] or timeline_notes
        decision_gates = [str(item).strip() for item in data.get("decision_gates", []) if str(item).strip()] or decision_gates
    except (LLMError, ValueError):
        pass

    if not next_steps:
        next_steps = [
            "Validate client mode and scope boundaries.",
            "Confirm phase-1 products, integrations, and reporting obligations.",
            "Lock the proposal template and evidence set before generation.",
        ]
    if not risks:
        risks = ["Generic or mixed-context evidence may leak into the proposal if metadata is incomplete."]
    if not verifications:
        verifications = ["Verify document names, current system, and phase split before drafting."]
    if not milestones:
        milestones = [
            "Lock intake scope and module list.",
            "Confirm the phase split and delivery model.",
            "Freeze evidence set and proposal template before generation.",
        ]
    if not open_questions:
        open_questions = ["Are there any modules, channels, or interfaces that must be deferred or excluded?"]
    if not timeline_notes:
        timeline_notes = ["Use TIM stage gates to turn the module list into a delivery calendar."]
    if not decision_gates:
        decision_gates = ["Freeze scope, evidence, architecture, and commercial assumptions before final drafting."]

    next_steps = [item for i, item in enumerate(next_steps) if item and item not in next_steps[:i]]
    risks = [item for i, item in enumerate(risks) if item and item not in risks[:i]]
    verifications = [item for i, item in enumerate(verifications) if item and item not in verifications[:i]]
    milestones = [item for i, item in enumerate(milestones) if item and item not in milestones[:i]]
    open_questions = [item for i, item in enumerate(open_questions) if item and item not in open_questions[:i]]
    timeline_notes = [item for i, item in enumerate(timeline_notes) if item and item not in timeline_notes[:i]]
    decision_gates = [item for i, item in enumerate(decision_gates) if item and item not in decision_gates[:i]]

    return PlannerResponse(
        next_steps=next_steps[:10],
        risks=risks[:10],
        verifications=verifications[:10],
        milestones=milestones[:8],
        open_questions=open_questions[:8],
        timeline_notes=timeline_notes[:8],
        manday_estimates=manday_estimates[:8],
        role_assignments=role_assignments[:8],
        decision_gates=decision_gates[:8],
    )
