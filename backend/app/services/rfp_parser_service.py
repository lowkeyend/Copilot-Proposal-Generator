from __future__ import annotations

import json
import re
from typing import Any

from app.models.schemas import (
    IntakeProfile,
    ParsedField,
    RfpParseResponse,
)
from app.services.llm_service import LLMError, get_llm
from app.services.questionnaire_service import load_questionnaire_questions
from app.services.knowledge_ingest_service import get_knowledge_ingest


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
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _compact_value(text: str, limit_words: int = 14) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^[\-\*\u2022]+\s*", "", cleaned)
    cleaned = re.sub(r"^(?:answer|value|details|summary|scope|phase|methodology)\s*[:\-]\s*", "", cleaned, flags=re.I)
    parts = re.split(r"[;•\n\r]+", cleaned)
    candidate = parts[0].strip() if parts else cleaned
    for separator in [" - ", " | ", ". "]:
        if separator in candidate:
            candidate = candidate.split(separator, 1)[0].strip()
    words = candidate.split()
    if len(words) > limit_words:
        candidate = " ".join(words[:limit_words])
    return candidate.strip(" ,;:-")


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]


def _is_long_or_sentential(text: str) -> bool:
    cleaned = _clean(text)
    if not cleaned:
        return False
    words = cleaned.split()
    return len(words) > 12 or any(token in cleaned.lower() for token in [" the ", " that ", " which ", " because ", " therefore "])


def _normalize_field_value(text: str) -> str:
    cleaned = _compact_value(text, 12)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^(?:currently|current|existing|target|proposed|planned)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I)
    cleaned = cleaned.replace('"', "").replace("'", "")
    return _compact_value(cleaned, 12)


def _field_word_limit(key: str) -> int:
    long_keys = (
        "products",
        "interfaces",
        "channels",
        "module_list",
        "scope",
        "phases",
        "launch_plan",
        "integration_scope",
        "api_scope",
        "reporting_scope",
        "implementation_stages",
        "testing_strategy",
        "migration_strategy",
        "security_requirements",
        "compliance_requirements",
        "customizations_required",
        "dependencies",
        "open_issues",
        "risk_model",
        "next_steps",
    )
    return 42 if any(token in key for token in long_keys) else 14


def _normalize_field_value_for_key(key: str, text: str) -> str:
    limit = _field_word_limit(key)
    cleaned = _compact_value(text, limit)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^(?:currently|current|existing|target|proposed|planned)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I)
    cleaned = cleaned.replace('"', "").replace("'", "")
    return _compact_value(cleaned, limit)


def _chunk_text(text: str, chunk_size: int = 1800, overlap: int = 150) -> list[str]:
    lines = _split_lines(text)
    if not lines:
        return [text] if text else []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        if current and current_len + len(line) + 1 > chunk_size:
            chunks.append(" ".join(current).strip())
            tail: list[str] = []
            tail_len = 0
            for prior in reversed(current):
                if tail_len + len(prior) > overlap:
                    break
                tail.insert(0, prior)
                tail_len += len(prior)
            current = [*tail, line]
            current_len = sum(len(part) for part in current)
        else:
            current.append(line)
            current_len += len(line) + 1
    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _find_excerpt(text: str, needles: list[str]) -> str:
    lowered = text.lower()
    for needle in needles:
        idx = lowered.find(needle.lower())
        if idx != -1:
            start = max(0, idx - 60)
            end = min(len(text), idx + len(needle) + 120)
            return _clean(text[start:end])
    return ""


def _clean_list_block(block: str) -> list[str]:
    values: list[str] = []
    for line in _split_lines(block):
        cleaned = re.sub(r"^(?:[-*\u2022]|\d+[.)])\s*", "", line.strip())
        cleaned = re.sub(r"^(?:Phase\s+\d+\s*(?:[-:\u2013\u2014])?|MVP\s*[:\-]?)\s*", "", cleaned, flags=re.I)
        if not cleaned or cleaned.lower() in {"answer:", "answer"}:
            continue
        if cleaned.endswith(":"):
            continue
        values.append(cleaned.strip(" ;,"))
    return values


def _phase_block(answer: str, phase_label: str) -> str:
    labels = ["Phase 1", "Phase 2", "Phase 3", "Subsequent Phases"]
    stop_labels = "|".join(re.escape(label) for label in labels if label != phase_label)
    pattern = rf"{phase_label}[^\n]*:?\s*\n(?P<body>.*?)(?=\n(?:{stop_labels})\b|\Z)"
    match = re.search(pattern, answer, flags=re.I | re.S)
    return match.group("body").strip() if match else ""


def _questionnaire_answers(text: str) -> dict[int, str]:
    answers: dict[int, str] = {}
    pattern = re.compile(r"\bQ(\d+)\.\s+.*?Answer:\s*(.*?)(?=\s+Q\d+\.|\Z)", re.I | re.S)
    for match in pattern.finditer(text):
        answers[int(match.group(1))] = match.group(2).strip()
    return answers


def _hits(answer: str, options: list[str]) -> list[str]:
    low = answer.lower()
    return [option for option in options if option.lower() in low]


def _extract_questionnaire_signals(text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    answers = _questionnaire_answers(text)
    fields: dict[str, Any] = {}
    intake_patch: dict[str, Any] = {}

    if 1 in answers:
        q1 = answers[1]
        phase_1 = _clean_list_block(_phase_block(q1, "MVP")) or _clean_list_block(_phase_block(q1, "Phase 1"))
        subsequent = _clean_list_block(_phase_block(q1, "Subsequent Phases"))
        segments = []
        scan_values = [*phase_1, *subsequent, q1]
        for value in scan_values:
            if "retail" in value.lower():
                segments.append("Retail")
            if "sme" in value.lower():
                segments.append("SME")
            if "corporate" in value.lower():
                segments.append("Corporate")
            if "treasury" in value.lower():
                segments.append("Treasury")
        intake_patch["launch_segments"] = list(dict.fromkeys(segments))
        fields["target_business_units"] = ", ".join(intake_patch["launch_segments"])
        fields["scope_summary"] = "Phased regulatory go-live followed by expanded corporate and treasury scope"

    if 2 in answers:
        q2 = answers[2]
        p1 = _clean_list_block(_phase_block(q2, "Phase 1"))
        p2 = _clean_list_block(_phase_block(q2, "Phase 2"))
        if not p1:
            p1 = _hits(q2, TECH_VISTA_BASELINE["phase_1_products"])
        if not p2:
            p2 = _hits(q2, TECH_VISTA_BASELINE["phase_2_products"])
        intake_patch["phase_1_products"] = p1
        intake_patch["phase_2_products"] = p2
        intake_patch["module_list"] = list(dict.fromkeys([*p1, *p2]))
        fields["phase_1_products"] = ", ".join(p1)
        fields["phase_2_products"] = ", ".join(p2)
        fields["phase_1_scope"] = ", ".join(p1[:8])
        fields["phase_2_scope"] = ", ".join(p2[:8])
        fields["module_list"] = ", ".join(intake_patch["module_list"][:16])
        fields["target_modules"] = fields["module_list"]

    if 3 in answers:
        q3 = answers[3]
        p1 = _clean_list_block(_phase_block(q3, "Phase 1"))
        p2 = _clean_list_block(_phase_block(q3, "Phase 2"))
        if not p1:
            p1 = _hits(q3, TECH_VISTA_BASELINE["phase_1_interfaces"])
        if not p2:
            p2 = _hits(q3, TECH_VISTA_BASELINE["phase_2_interfaces"])
        intake_patch["regulatory_interfaces_phase_1"] = p1
        intake_patch["regulatory_interfaces_phase_2"] = p2
        fields["phase_1_interfaces"] = ", ".join(p1)
        fields["phase_2_interfaces"] = ", ".join(p2)
        fields["integration_scope"] = ", ".join([*p1, *p2])

    if 4 in answers:
        q4 = answers[4]
        p1 = _clean_list_block(_phase_block(q4, "Phase 1"))
        p2 = _clean_list_block(_phase_block(q4, "Phase 2"))
        if not p1:
            p1 = _hits(q4, ["Branch / Teller", "ATM", "AML", "Payment switch"])
        if not p2:
            p2 = _hits(q4, ["Mobile & Internet Banking", "SWIFT", "CRM / Call Center", "ERP / Finance", "Notifications/AI chatbots"])
        intake_patch["channels_phase_1"] = p1
        intake_patch["channels_phase_2"] = p2
        fields["phase_1_channels"] = ", ".join(p1)
        fields["phase_2_channels"] = ", ".join(p2)
        fields["api_scope"] = ", ".join([*p1, *p2])

    if 5 in answers:
        value = _clean_list_block(answers[5])
        fields["middleware_platform"] = value[0] if value else _compact_value(answers[5], 18)
        intake_patch["middleware_platform"] = fields["middleware_platform"]

    if 6 in answers:
        fields["reporting_scope"] = "15-20 regulatory reports including balance sheet, liquidity, capital adequacy, AML, deposits, and payments"

    if 7 in answers:
        low = answers[7].lower()
        if "temenos reporting" in low:
            intake_patch["reporting_platform"] = "Temenos Reporting"
            fields["reporting_platform"] = "Temenos Reporting"
        if "tdh" in low:
            intake_patch["data_warehouse_platform"] = "Temenos TDH"
            fields["data_warehouse_platform"] = "Temenos TDH"

    if 8 in answers:
        fields["database_platform"] = "Oracle Database 19c or higher"
        intake_patch["database_platform"] = fields["database_platform"]

    if 9 in answers:
        fields["hosting_model"] = "AWS Cloud"
        intake_patch["hosting_model"] = "AWS Cloud"

    if 10 in answers:
        fields["container_platform"] = "Not mandatory for MVP; may be considered later"
        intake_patch["container_platform"] = fields["container_platform"]

    q11 = answers.get(11, text)
    for year in (1, 2, 3):
        match = re.search(rf"Year\s*{year}\s*:\s*([\d,]+)\s*customers\s*/\s*([\d,]+)\s*accounts", q11, flags=re.I)
        if match:
            intake_patch[f"target_customers_year_{year}"] = match.group(1)
            intake_patch[f"target_accounts_year_{year}"] = match.group(2)
            fields[f"target_customers_year_{year}"] = match.group(1)
            fields[f"target_accounts_year_{year}"] = match.group(2)
    if fields.get("target_customers_year_3") and fields.get("target_accounts_year_3"):
        fields["target_users"] = (
            f"Year 3 target: {fields['target_customers_year_3']} customers / "
            f"{fields['target_accounts_year_3']} accounts"
        )

    if 12 in answers or re.search(r"Phase\s*1\s*:\s*March\s*2026", text, flags=re.I):
        fields["launch_plan"] = "Phase 1 March 2026 regulatory go-live, Phase 2 after 2-3 months, Phase 3 after another 2-3 months"
        fields["phase_3_scope"] = "Phase 3 starts 2-3 months after Phase 2"
        fields["implementation_stages"] = fields["launch_plan"]
        fields["delivery_phases"] = fields["launch_plan"]
        intake_patch["launch_plan"] = fields["launch_plan"]

    if fields:
        fields["project_mode"] = "implementation"
        fields["client_expectations"] = "Regulatory go-live stability, phased rollout, and approval-dependent expansion"
        fields["desired_capabilities"] = "Core deposits, onboarding, payments, regulatory reporting, channels, and phased digital expansion"
    return fields, intake_patch


def _guess_project_mode(text: str) -> str:
    lowered = text.lower()
    upgrade_terms = ("upgrade", "migration", "replace", "modernization", "modernisation", "existing system")
    if any(term in lowered for term in upgrade_terms):
        return "upgrade"
    implementation_terms = ("implementation", "new bank", "greenfield", "launch", "rollout")
    if any(term in lowered for term in implementation_terms):
        return "implementation"
    return "unknown"


def _guess_field_value(text: str, patterns: list[str]) -> str:
    excerpt = _find_excerpt(text, patterns)
    return _compact_value(excerpt, 16)


def _clean_candidate_value(value: str, limit_words: int = 24) -> str:
    cleaned = _clean(value)
    cleaned = re.sub(r"^[\-\*\u2022\d.)\s]+", "", cleaned)
    cleaned = re.sub(r"^(?:answer|response|value|details|required|requirement)\s*[:\-]\s*", "", cleaned, flags=re.I)
    cleaned = cleaned.strip(" ,;:-")
    if not cleaned:
        return ""
    if len(cleaned.split()) > limit_words:
        cleaned = " ".join(cleaned.split()[:limit_words]).rstrip(",;:-")
    if re.search(r"\b(lorem ipsum|table of contents|copyright|confidential)\b", cleaned, flags=re.I):
        return ""
    return cleaned


def _extract_labeled_value(text: str, labels: list[str], limit_words: int = 28) -> str:
    lines = _split_lines(text)
    if not lines:
        return ""
    label_pattern = "|".join(re.escape(label) for label in labels if label)
    if not label_pattern:
        return ""
    for index, line in enumerate(lines):
        match = re.search(rf"\b(?:{label_pattern})\b\s*[:\-–]\s*(.+)$", line, flags=re.I)
        if match:
            value = _clean_candidate_value(match.group(1), limit_words)
            if value and not any(value.lower() == label.lower() for label in labels):
                return value
        if re.fullmatch(rf".*\b(?:{label_pattern})\b\s*[:\-–]?\s*", line, flags=re.I):
            following = []
            for next_line in lines[index + 1 : index + 4]:
                if re.search(r":\s*$", next_line) or re.fullmatch(r"[A-Z][A-Z0-9 /&().-]{5,}", next_line):
                    break
                following.append(next_line)
            value = _clean_candidate_value("; ".join(following), limit_words)
            if value:
                return value
    return ""


def _extract_known_value(text: str, key: str, limit_words: int = 28) -> str:
    lowered = text.lower()
    if key in {"current_version", "target_version"}:
        version_patterns = [
            r"\b(?:T24|Transact|Temenos)\s*(?:R)?\s?(\d{2,4}(?:\.\d+)*)\b",
            r"\bR(?:19|20|21|22|23|24|25|26)\b",
        ]
        matches = []
        for pattern in version_patterns:
            matches.extend(re.findall(pattern, text, flags=re.I))
        if matches:
            prefix = "Target" if key == "target_version" else "Current"
            if key == "target_version" and re.search(r"\b(upgrade|target|to|future)\b.{0,50}\b(R?\d{2,4}(?:\.\d+)*)", text, flags=re.I):
                return _clean_candidate_value(matches[-1], 8)
            return _clean_candidate_value(matches[0], 8) if prefix == "Current" else _clean_candidate_value(matches[-1], 8)
    if key == "database_platform":
        match = re.search(r"\bOracle(?:\s+Database)?\s*(?:19c|21c|23c|[0-9.]+)?(?:\s+or higher)?\b", text, flags=re.I)
        if match:
            return _clean_candidate_value(match.group(0), 10)
    if key == "hosting_model":
        for value in ("AWS Cloud", "Azure Cloud", "Google Cloud", "On-premise", "On premise", "Private Cloud", "Hybrid Cloud"):
            if value.lower() in lowered:
                return value.replace("On premise", "On-premise")
    if key == "container_platform":
        for value in ("Red Hat OpenShift", "OpenShift", "Kubernetes", "Docker"):
            if value.lower() in lowered:
                return value
    if key == "reporting_platform":
        for value in ("Temenos Reporting", "Power BI", "Tableau", "OBIEE", "Crystal Reports"):
            if value.lower() in lowered:
                return value
    if key == "data_warehouse_platform":
        if "temenos tdh" in lowered or re.search(r"\btdh\b", lowered):
            return "Temenos TDH"
    if key == "implementation_methodology":
        if re.search(r"\bTIM\b|Temenos Implementation Methodology", text, flags=re.I):
            return "TIM"
    if key == "delivery_model":
        if "big bang" in lowered:
            return "Single Big Bang"
        if "mvp" in lowered or "phased" in lowered:
            return "Phased MVP"
    return ""


def _extract_field_value(text: str, key: str, label: str, needles: list[str], limit_words: int) -> str:
    known = _extract_known_value(text, key, limit_words)
    if known:
        return known
    label_value = _extract_labeled_value(text, [label, *needles], limit_words)
    if label_value:
        return label_value
    return ""


def _guess_intake(text: str) -> IntakeProfile:
    lowered = text.lower()
    intake = IntakeProfile()
    intake.project_mode = _guess_project_mode(text)
    module_terms = [
        "deposit", "savings", "current account", "casa", "customer onboarding", "kyc",
        "card", "payment", "lending", "loan", "trade finance", "treasury", "cash management",
        "internet banking", "mobile banking", "crm", "fx", "liquidity", "settlement",
    ]

    if "retail" in lowered:
        intake.launch_segments.append("Retail")
    if "sme" in lowered or "small and medium" in lowered:
        intake.launch_segments.append("SME")
    if "corporate" in lowered:
        intake.launch_segments.append("Corporate")
    if "treasury" in lowered:
        intake.launch_segments.append("Treasury")

    if "tim" in lowered:
        intake.implementation_methodology = "TIM"
    if "mvp" in lowered:
        intake.delivery_model = "Phased MVP"
    if "big bang" in lowered:
        intake.delivery_model = "Single Big Bang"

    if "oracle" in lowered:
        intake.database_platform = "Oracle 19c+"
    if "aws" in lowered:
        intake.hosting_model = "AWS Cloud"
    if "openshift" in lowered or "openshift" in lowered:
        intake.container_platform = "Red Hat OpenShift"
    if "temenos tdh" in lowered or "tdh" in lowered:
        intake.data_warehouse_platform = "Temenos TDH"
    if "temenos reporting" in lowered:
        intake.reporting_platform = "Temenos Reporting"
    if "middleware" in lowered or "esb" in lowered:
        intake.middleware_platform = "ESB / API Gateway"

    module_hits = []
    for term in module_terms:
        if term in lowered:
            module_hits.append(term.title())
    if "casa" in lowered:
        module_hits.append("CASA")
    intake.module_list = list(dict.fromkeys(module_hits))

    return intake


def _field(key: str, label: str, value: str, category: str, text: str) -> ParsedField:
    value = _compact_value(value, 14)
    return ParsedField(
        key=key,
        label=label,
        value=value,
        category=category,
        confidence=0.7 if value else 0.15,
        source_excerpt=_compact_value(_find_excerpt(text, [value] if value else []), 18),
    )


def _multi_fields(title: str, values: list[str], category: str, source_text: str) -> list[ParsedField]:
    fields: list[ParsedField] = []
    for index, value in enumerate(values, start=1):
        fields.append(
            ParsedField(
                key=f"{title.lower().replace(' ', '_')}_{index}",
                label=f"{title} {index}",
                value=value,
                category=category,
                confidence=0.9 if value else 0.25,
                source_excerpt=_find_excerpt(source_text, [value] if value else []),
            )
        )
    return fields


FIELD_SPECS: list[tuple[str, str, str, list[str]]] = [
    ("rfp_title", "RFP Title", "Overview", ["rfp title", "request for proposal", "tender title", "proposal title"]),
    ("client_name", "Client Name", "Overview", ["client name", "bank name", "institution name", "issued by"]),
    ("project_mode", "Project Mode", "Scope", ["upgrade", "implementation", "greenfield", "migration"]),
    ("scope_summary", "Scope Summary", "Overview", ["scope", "objective", "purpose", "summary"]),
    ("target_country", "Target Country", "Overview", ["country", "jurisdiction", "territory"]),
    ("target_city", "Target City", "Overview", ["city", "location", "head office"]),
    ("submission_deadline", "Submission Deadline", "Commercial", ["submission deadline", "due date", "proposal due", "bid due"]),
    ("evaluation_criteria", "Evaluation Criteria", "Commercial", ["evaluation criteria", "award criteria", "scoring"]),
    ("current_system", "Current System", "Upgrade", ["current system", "existing system", "present system", "legacy system"]),
    ("current_version", "Current Version", "Upgrade", ["current version", "existing version", "version"]),
    ("current_modules", "Current Modules", "Upgrade", ["current modules", "modules in use", "installed modules"]),
    ("current_gaps", "Current Gaps", "Upgrade", ["current gaps", "pain points", "challenges", "limitations"]),
    ("current_data_volume", "Current Data Volume", "Upgrade", ["data volume", "transaction volume", "account volume"]),
    ("current_infrastructure", "Current Infrastructure", "Infrastructure", ["current infrastructure", "existing infrastructure", "on premise"]),
    ("current_hardware", "Current Hardware", "Infrastructure", ["hardware", "servers", "appliance"]),
    ("current_processes", "Current Processes", "Upgrade", ["process", "workflow", "business process"]),
    ("target_version", "Target Version", "Upgrade", ["target version", "upgrade to", "move to", "new release"]),
    ("target_modules", "Target Modules", "Scope", ["target modules", "modules required", "functional scope"]),
    ("desired_capabilities", "Desired Capabilities", "Scope", ["desired capabilities", "wanted", "required capabilities"]),
    ("target_business_units", "Target Business Units", "Scope", ["business units", "segments", "lines of business"]),
    ("target_users", "Target Users", "Scope", ["users", "user base", "end users"]),
    ("target_customers_year_1", "Target Customers Year 1", "Scope", ["year 1", "target customers"]),
    ("target_customers_year_2", "Target Customers Year 2", "Scope", ["year 2", "target customers"]),
    ("target_customers_year_3", "Target Customers Year 3", "Scope", ["year 3", "target customers"]),
    ("target_accounts_year_1", "Target Accounts Year 1", "Scope", ["year 1", "target accounts"]),
    ("target_accounts_year_2", "Target Accounts Year 2", "Scope", ["year 2", "target accounts"]),
    ("target_accounts_year_3", "Target Accounts Year 3", "Scope", ["year 3", "target accounts"]),
    ("target_branches", "Target Branches", "Scope", ["branches", "branch network"]),
    ("target_geographies", "Target Geographies", "Scope", ["geographies", "locations", "countries"]),
    ("module_list", "Module List", "Scope", ["module", "modules", "functional module", "component"]),
    ("phase_1_scope", "Phase 1 Scope", "Delivery", ["phase 1", "phase one", "mvp", "go live"]),
    ("phase_2_scope", "Phase 2 Scope", "Delivery", ["phase 2", "phase two", "subsequent phase"]),
    ("phase_3_scope", "Phase 3 Scope", "Delivery", ["phase 3", "phase three", "later phase"]),
    ("phase_1_products", "Phase 1 Products", "Scope", ["phase 1 products", "first phase products", "initial products"]),
    ("phase_2_products", "Phase 2 Products", "Scope", ["phase 2 products", "second phase products", "later products"]),
    ("phase_1_interfaces", "Phase 1 Interfaces", "Integration", ["phase 1 interfaces", "first phase interfaces", "initial interfaces"]),
    ("phase_2_interfaces", "Phase 2 Interfaces", "Integration", ["phase 2 interfaces", "second phase interfaces"]),
    ("phase_1_channels", "Phase 1 Channels", "Channel", ["phase 1 channels", "first phase channels", "initial channels"]),
    ("phase_2_channels", "Phase 2 Channels", "Channel", ["phase 2 channels", "second phase channels"]),
    ("middleware_platform", "Middleware Platform", "Architecture", ["middleware", "integration framework", "esb", "api gateway"]),
    ("integration_scope", "Integration Scope", "Integration", ["integration", "interface", "api", "connectivity"]),
    ("api_scope", "API Scope", "Integration", ["api", "rest", "soap", "gateway"]),
    ("reporting_platform", "Reporting Platform", "Reporting", ["reporting", "mis", "regulatory reporting"]),
    ("reporting_scope", "Reporting Scope", "Reporting", ["report", "dashboard", "mis", "analytics"]),
    ("data_warehouse_platform", "Data Warehouse Platform", "Reporting", ["data warehouse", "tdh", "warehouse"]),
    ("analytics_scope", "Analytics Scope", "Reporting", ["analytics", "insight", "dashboard", "bi"]),
    ("database_platform", "Database Platform", "Infrastructure", ["database", "oracle", "sql server", "postgres"]),
    ("hosting_model", "Hosting Model", "Infrastructure", ["hosting", "cloud", "aws", "azure", "on premise"]),
    ("container_platform", "Container Platform", "Infrastructure", ["container", "kubernetes", "openshift", "docker"]),
    ("security_requirements", "Security Requirements", "Security", ["security", "encryption", "iam", "audit", "logging"]),
    ("compliance_requirements", "Compliance Requirements", "Security", ["compliance", "regulatory", "policy", "aml", "sanctions"]),
    ("migration_strategy", "Migration Strategy", "Delivery", ["migration strategy", "adopt not adapt", "conversion"]),
    ("cutover_strategy", "Cutover Strategy", "Delivery", ["cutover", "go live", "switch over"]),
    ("testing_strategy", "Testing Strategy", "Delivery", ["testing", "sit", "uat", "performance test"]),
    ("training_strategy", "Training Strategy", "Delivery", ["training", "enablement", "knowledge transfer"]),
    ("change_management", "Change Management", "Delivery", ["change management", "adoption", "readiness"]),
    ("implementation_stages", "Implementation Stages", "Delivery", ["stages", "stage gate", "milestone", "phase"]),
    ("delivery_phases", "Delivery Phases", "Delivery", ["phase 1", "phase 2", "phase 3", "waves"]),
    ("customizations_required", "Customizations Required", "Scope", ["customization", "customisations", "configuration changes"]),
    ("client_requests", "Client Requests", "Commercial", ["request", "requested", "please include"]),
    ("client_expectations", "Client Expectations", "Commercial", ["expectation", "expectations", "must", "should"]),
    ("non_functional_requirements", "Non-Functional Requirements", "Security", ["performance", "availability", "scalability", "nfr"]),
    ("acceptance_details", "Acceptance Details", "Commercial", ["acceptance", "sign off", "signoff"]),
    ("cutover_window", "Cutover Window", "Delivery", ["cutover window", "window", "downtime"]),
    ("training_needs", "Training Needs", "Delivery", ["training", "workshop", "knowledge transfer"]),
    ("hypercare_needs", "Hypercare Needs", "Delivery", ["hypercare", "post go live", "support period"]),
    ("launch_plan", "Launch Plan", "Delivery", ["launch plan", "target dates", "go-live"]),
    ("governance_model", "Governance Model", "Governance", ["governance", "steering committee", "pmO"]),
    ("pmo_structure", "PMO Structure", "Governance", ["pmo", "project management office", "project manager"]),
    ("resourcing_model", "Resourcing Model", "Governance", ["resources", "team", "staffing", "resourcing"]),
    ("risk_model", "Risk Model", "Governance", ["risk", "issue", "mitigation"]),
    ("assumptions", "Assumptions", "Governance", ["assumption", "assumes", "based on"]),
    ("dependencies", "Dependencies", "Governance", ["dependency", "depends", "prerequisite"]),
    ("open_issues", "Open Issues", "Governance", ["open issues", "questions", "clarification"]),
    ("support_model", "Support Model", "Delivery", ["support", "hypercare", "managed service"]),
    ("sla_requirements", "SLA Requirements", "Commercial", ["sla", "service level", "availability"]),
    ("maintenance_scope", "Maintenance Scope", "Commercial", ["maintenance", "support", "warranty"]),
    ("warranty_period", "Warranty Period", "Commercial", ["warranty", "defect liability"]),
    ("acceptance_criteria", "Acceptance Criteria", "Commercial", ["acceptance", "sign off", "criteria"]),
    ("commercials", "Commercials", "Commercial", ["commercial", "pricing", "cost", "budget"]),
    ("bid_submission", "Bid Submission", "Commercial", ["submission", "bid submission", "proposal format"]),
    ("rfp_notes", "RFP Notes", "Notes", ["note", "instruction", "remark", "annexure"]),
]


def _build_spec_field(text: str, intake: IntakeProfile, field_map: dict[str, Any], spec: tuple[str, str, str, list[str]]) -> ParsedField:
    key, label, category, needles = spec
    raw_value = field_map.get(key, "")
    if not raw_value and hasattr(intake, key):
        raw_value = getattr(intake, key)
    if not raw_value:
        raw_value = _extract_field_value(text, key, label, needles, 36)
    if isinstance(raw_value, list):
        raw_value = ", ".join(str(item) for item in raw_value if str(item).strip())
    list_like_keys = (
        "products",
        "interfaces",
        "channels",
        "module_list",
        "scope",
        "phases",
        "launch_plan",
        "integration_scope",
        "api_scope",
        "reporting_scope",
    )
    limit = 36 if any(token in key for token in list_like_keys) else 14
    value = _compact_value(str(raw_value).strip(), limit)
    return ParsedField(
        key=key,
        label=label,
        value=value,
        category=category,
        confidence=0.82 if value else 0.2,
        source_excerpt=_compact_value(_find_excerpt(text, [value] if value else needles[:2]), 18),
    )


async def _rewrite_fields_to_concise_answers(
    fields: list[dict[str, Any]],
    document_text: str,
    model: str | None,
) -> list[dict[str, Any]]:
    if not fields or not get_llm().available:
        return fields

    prompt = f"""Rewrite the RFP field values into concise answer form.

Rules:
- Return STRICT JSON only.
- Keep every answer short, specific, and factual.
- Do not copy sentences from the document.
- Do not mention "the document", "the RFP", "states", "mentions", or any source language.
- Prefer noun phrases, names, versions, dates, counts, and short facts.
- Keep scalar values to 12 words or fewer.
- For phase scope, module, product, interface, channel, testing, migration, dependency, and risk fields, keep concise grouped facts up to 40 words.
- If a value is unknown or unsupported, return an empty string.

Input fields:
{json.dumps(fields, indent=2)[:90000]}

Document context:
{document_text[:50000]}

Return:
{{
  "fields": [
    {{"key":"", "value":"", "notes":""}}
  ]
}}"""

    try:
        data = await get_llm().chat_json(
            [
                {
                    "role": "system",
                    "content": "You normalize RFP field answers into concise, non-extractive JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0.0,
            max_tokens=1800,
        )
    except (LLMError, ValueError):
        return fields

    if not isinstance(data, dict) or not isinstance(data.get("fields"), list):
        return fields

    normalized_by_key: dict[str, dict[str, Any]] = {}
    for item in data["fields"]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        normalized_by_key[key] = item

    rewritten: list[dict[str, Any]] = []
    for item in fields:
        key = str(item.get("key", "")).strip()
        base_value = str(item.get("value", "")).strip()
        rewrite = normalized_by_key.get(key, {})
        candidate = str(rewrite.get("value", "")).strip() or base_value
        candidate = _normalize_field_value_for_key(key, candidate)
        if _is_long_or_sentential(candidate) and _field_word_limit(key) <= 14:
            candidate = _normalize_field_value_for_key(key, candidate)
        if not candidate and base_value:
            candidate = _normalize_field_value_for_key(key, base_value)
        rewritten.append(
            {
                **item,
                "value": candidate,
                "notes": str(rewrite.get("notes", item.get("notes", "")) or "").strip(),
            }
        )
    return rewritten


async def parse_rfp_documents(files, model: str | None = None) -> RfpParseResponse:
    docs = await get_knowledge_ingest().parse_files(files)
    if not docs:
        raise RuntimeError("No readable content found in the uploaded files.")

    filename = docs[0].filename if len(docs) == 1 else f"{len(docs)} documents"
    text = "\n\n".join(doc.text for doc in docs if doc.text)
    analysis_chunks = _chunk_text(text)
    questions = load_questionnaire_questions()

    prompt = f"""You extract proposal intake data from an RFP or tender document.
Return STRICT JSON with these keys:
{{
  "title": "",
  "project_mode": "implementation|upgrade|unknown",
  "summary": "",
  "storyline": "",
  "fields": [
    {{"key":"","label":"","value":"","category":"","confidence":0.0,"source_excerpt":"","notes":""}}
  ],
  "intake": {{
    "project_mode": "implementation|upgrade|unknown",
    "launch_segments": [],
    "module_list": [],
    "phase_1_products": [],
    "phase_2_products": [],
    "regulatory_interfaces_phase_1": [],
    "regulatory_interfaces_phase_2": [],
    "channels_phase_1": [],
    "channels_phase_2": [],
    "middleware_platform": "",
    "reporting_platform": "",
    "database_platform": "",
    "hosting_model": "",
    "container_platform": "",
    "data_warehouse_platform": "",
    "implementation_methodology": "",
    "delivery_model": "",
    "current_system": "",
    "current_version": "",
    "target_version": "",
    "upgrade_strategy": "",
    "hardware_requirements": "",
    "infrastructure_requirements": "",
    "current_gaps": "",
    "desired_capabilities": "",
    "target_customers_year_1": "",
    "target_customers_year_2": "",
    "target_customers_year_3": "",
    "target_accounts_year_1": "",
    "target_accounts_year_2": "",
    "target_accounts_year_3": "",
    "launch_plan": "",
    "questionnaire_notes": ""
  }},
  "missing_fields": [],
  "next_steps": []
}}

Use the questionnaire as a checklist:
{json.dumps(questions, indent=2)}

Document chunks:
{json.dumps(analysis_chunks[:12], indent=2)[:140000]}"""
    prompt += """

Field rules:
- Every field value must be a concise answer, not a copied sentence.
- Prefer short facts, names, versions, dates, counts, or noun phrases.
- Do not include source language such as 'the document states' or 'according to the RFP'.
- If the answer is unclear, leave the value empty.
- Keep output normalized and consistent across headings.
"""

    llm_data: dict[str, Any] = {}
    try:
        llm_data = await get_llm().chat_json(
            [
                {
                    "role": "system",
                    "content": "You are a strict JSON extraction engine. Do not add commentary.",
                },
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0.1,
            max_tokens=2200,
        )
    except (LLMError, ValueError):
        llm_data = {}

    intake = _guess_intake(text)
    if isinstance(llm_data.get("intake"), dict):
        incoming = llm_data["intake"]
        for field in IntakeProfile.model_fields:
            value = incoming.get(field)
            if value not in (None, "", []):
                setattr(intake, field, value)

    questionnaire_fields, questionnaire_intake = _extract_questionnaire_signals(text)
    for field, value in questionnaire_intake.items():
        if value not in (None, "", []):
            setattr(intake, field, value)

    fields: list[ParsedField] = []
    field_map: dict[str, Any] = {}
    if isinstance(llm_data.get("fields"), list):
        for item in llm_data["fields"][:40]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            if key:
                field_map[key] = item.get("value", "")
    field_map.update(questionnaire_fields)

    for spec in FIELD_SPECS:
        built = _build_spec_field(text, intake, field_map, spec)
        fields.append(built)

    fields.extend(
        [
            _field("client", "Client / Institution", _guess_field_value(text, ["bank", "institution", "client"]), "General", text),
            _field("project_mode", "Project Mode", intake.project_mode, "Scope", text),
            _field("current_system", "Current System", intake.current_system or _guess_field_value(text, ["current system", "existing system", "present system"]), "Upgrade", text),
            _field("current_version", "Current Version", intake.current_version or _guess_field_value(text, ["current version", "version"]), "Upgrade", text),
            _field("target_version", "Target Version", intake.target_version or _guess_field_value(text, ["target version", "future version", "upgrade to"]), "Upgrade", text),
            _field("upgrade_strategy", "Upgrade Strategy", intake.upgrade_strategy or _guess_field_value(text, ["upgrade strategy", "migration approach", "cutover"]), "Upgrade", text),
            _field("hosting_model", "Hosting Model", intake.hosting_model, "Infrastructure", text),
            _field("database_platform", "Database Platform", intake.database_platform, "Infrastructure", text),
            _field("middleware_platform", "Middleware Platform", intake.middleware_platform, "Infrastructure", text),
            _field("reporting_platform", "Reporting Platform", intake.reporting_platform, "Reporting", text),
            _field("data_warehouse_platform", "Data Warehouse Platform", intake.data_warehouse_platform, "Reporting", text),
            _field("delivery_model", "Delivery Model", intake.delivery_model, "Delivery", text),
            _field("implementation_methodology", "Implementation Methodology", intake.implementation_methodology, "Delivery", text),
            _field("launch_plan", "Launch Plan", intake.launch_plan, "Delivery", text),
            _field("hardware_requirements", "Hardware Requirements", intake.hardware_requirements, "Infrastructure", text),
            _field("infrastructure_requirements", "Infrastructure Requirements", intake.infrastructure_requirements, "Infrastructure", text),
            _field("current_gaps", "Current Gaps", intake.current_gaps, "Upgrade", text),
            _field("desired_capabilities", "Desired Capabilities", intake.desired_capabilities, "Scope", text),
            _field("questionnaire_notes", "Questionnaire Notes", intake.questionnaire_notes, "Notes", text),
        ]
    )

    fields.extend(_multi_fields("Launch Segment", intake.launch_segments, "Scope", text))
    fields.extend(_multi_fields("Phase 1 Product", intake.phase_1_products, "Scope", text))
    fields.extend(_multi_fields("Phase 2 Product", intake.phase_2_products, "Scope", text))
    fields.extend(_multi_fields("Phase 1 Interface", intake.regulatory_interfaces_phase_1, "Integration", text))
    fields.extend(_multi_fields("Phase 2 Interface", intake.regulatory_interfaces_phase_2, "Integration", text))
    fields.extend(_multi_fields("Phase 1 Channel", intake.channels_phase_1, "Channel", text))
    fields.extend(_multi_fields("Phase 2 Channel", intake.channels_phase_2, "Channel", text))

    normalized_fields: list[dict[str, Any]] = [field.model_dump() for field in fields]
    normalized_fields = await _rewrite_fields_to_concise_answers(normalized_fields, text, model)
    for field in normalized_fields:
        key = str(field.get("key", "")).strip()
        if key in questionnaire_fields:
            limit = 36 if any(token in key for token in ("products", "interfaces", "channels", "module_list", "scope", "phases", "launch_plan")) else 14
            field["value"] = _compact_value(str(questionnaire_fields[key]), limit)
    fields = [ParsedField(**field) for field in normalized_fields]

    deduped_fields: list[ParsedField] = []
    seen_keys: set[str] = set()
    for field in fields:
        key = field.key.strip()
        if not key:
            continue
        if not field.value:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_fields.append(field)
    fields = deduped_fields

    if not fields:
        fields = [
            _field("client", "Client / Institution", _guess_field_value(text, ["bank", "institution", "client"]), "General", text),
            _field("project_mode", "Project Mode", intake.project_mode, "Scope", text),
        ]

    project_mode = str(llm_data.get("project_mode", "")).strip() or intake.project_mode
    title = str(llm_data.get("title", "")).strip()
    summary = str(llm_data.get("summary", "")).strip()
    missing_fields = [
        str(item)
        for item in llm_data.get("missing_fields", [])
        if str(item).strip()
    ]
    next_steps = [
        str(item)
        for item in llm_data.get("next_steps", [])
        if str(item).strip()
    ]

    if not title:
        title = docs[0].filename
    if not summary:
        summary = (
            f"Extracted {len(fields)} mapped fields from the uploaded RFP and "
            f"identified the project as {project_mode or 'unknown'}."
        )
    storyline = str(llm_data.get("storyline", "")).strip()
    if not storyline:
        storyline_parts = [
            f"{title or docs[0].filename} is interpreted as a {project_mode or 'unknown'} engagement.",
            f"Phase 1 should center on {', '.join(intake.phase_1_products[:4]) or 'the confirmed core scope'}.",
            f"Delivery is structured around {intake.delivery_model or 'the selected delivery model'} and TIM governance.",
        ]
        if intake.current_system or intake.current_version:
            lineage = intake.current_system or "the incumbent platform"
            if intake.current_version:
                lineage = f"{lineage} at version {intake.current_version}"
            storyline_parts.insert(1, f"The current landscape is {lineage}.")
        if intake.target_version:
            storyline_parts.append(f"The target state should validate the path to {intake.target_version}.")
        if intake.module_list:
            storyline_parts.append(f"Module coverage includes {', '.join(intake.module_list[:6])}.")
        storyline = " ".join(storyline_parts)
    if not next_steps:
        next_steps = [
            "Confirm the current system and target version.",
            "Validate phase-1 and phase-2 product scope.",
            "Map integrations, reporting, and infrastructure dependencies.",
        ]

    return RfpParseResponse(
        filename=filename,
        title=title,
        project_mode=project_mode if project_mode in {"implementation", "upgrade", "unknown"} else intake.project_mode,
        storyline=storyline,
        fields=fields,
        intake=intake,
        summary=summary,
        missing_fields=missing_fields,
        next_steps=next_steps,
    )
