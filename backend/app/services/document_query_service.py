from __future__ import annotations

import math
import re
from collections import Counter, OrderedDict
from typing import Iterable

from app.models.schemas import ChatMessage, DocumentQueryResponse, EvidenceChunk
from app.services.embedding_service import get_embedder
from app.services.llm_service import LLMError, get_llm
from app.services.qdrant_service import get_qdrant
from app.config import get_settings


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


_STOPWORDS = {
    "about",
    "according",
    "after",
    "also",
    "and",
    "answer",
    "are",
    "based",
    "between",
    "can",
    "compare",
    "could",
    "does",
    "document",
    "documents",
    "for",
    "from",
    "give",
    "have",
    "how",
    "into",
    "its",
    "list",
    "need",
    "needs",
    "only",
    "please",
    "proposal",
    "question",
    "say",
    "says",
    "should",
    "show",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "those",
    "what",
    "when",
    "where",
    "which",
    "with",
}

_SCOPE_TERMS = {
    "products": [
        "Temenos Transact",
        "Temenos Payments",
        "Finance & General Ledger",
        "Retail Banking",
        "Corporate Banking",
        "Lending",
        "Treasury",
        "Trade Finance",
        "Savings Accounts",
        "Current Accounts",
        "CASA",
        "Customer onboarding",
        "KYC",
        "Domestic interbank payments",
        "International transfers",
        "Retail lending",
        "SME lending",
        "Corporate lending",
    ],
    "interfaces": [
        "MMA regulatory reporting",
        "RTGS / ACH",
        "RTGS",
        "ACH",
        "AML & sanctions screening",
        "AML",
        "Sanctions screening",
        "ATM switch",
        "Identity verification",
        "Credit bureau",
        "Card schemes",
        "Government e-KYC",
        "e-KYC",
        "SWIFT",
    ],
    "channels": [
        "Branch / Teller",
        "Teller",
        "ATM",
        "Payment switch",
        "Mobile Banking",
        "Internet Banking",
        "Mobile & Internet Banking",
        "CRM / Call Center",
        "ERP / Finance",
        "Notifications",
        "AI chatbots",
    ],
}

_PLATFORM_PATTERNS = {
    "database": [
        r"\bOracle(?:\s+Database)?\s*(?:19c|21c|23c|[0-9.]+)?(?:\s+or higher)?\b",
        r"\bPostgreSQL\b",
        r"\bSQL Server\b",
    ],
    "hosting": [
        r"\bAWS Cloud\b",
        r"\bAzure Cloud\b",
        r"\bGoogle Cloud\b",
        r"\bPrivate Cloud\b",
        r"\bHybrid Cloud\b",
        r"\bOn[- ]premise\b",
    ],
    "reporting": [
        r"\bTemenos Reporting\b",
        r"\bTemenos TDH\b",
        r"\bTDH\b",
        r"\bPower BI\b",
        r"\bTableau\b",
    ],
    "container": [
        r"\bRed Hat OpenShift\b",
        r"\bOpenShift\b",
        r"\bKubernetes\b",
        r"\bDocker\b",
        r"\bnot mandatory\b",
    ],
}


def _query_terms(text: str) -> list[str]:
    return [token for token in _tokens(text) if token not in _STOPWORDS]


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        cleaned = re.sub(r"\s+", " ", item.strip(" .;:-\n\t"))
        key = cleaned.lower()
        if len(cleaned) < 6 or key in seen:
            continue
        seen.add(key)
        unique_items.append(cleaned)
    return unique_items


def _windowed_text(text: str, phase: str) -> str:
    labels = {
        "phase_1": ("phase 1", "phase one", "mvp"),
        "phase_2": ("phase 2", "phase two", "subsequent phase"),
    }[phase]
    stop_labels = ("phase 1", "phase one", "mvp", "phase 2", "phase two", "subsequent phase", "phase 3", "phase three")
    lowered = text.lower()
    windows: list[str] = []
    for label in labels:
        start = 0
        while True:
            idx = lowered.find(label, start)
            if idx == -1:
                break
            next_stops = [
                lowered.find(stop_label, idx + len(label))
                for stop_label in stop_labels
                if stop_label not in labels and lowered.find(stop_label, idx + len(label)) != -1
            ]
            end = min(next_stops) if next_stops else min(len(text), idx + 1200)
            windows.append(text[max(0, idx - 180) : min(len(text), end)])
            start = idx + len(label)
    return "\n".join(windows)


def _find_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for term in terms:
        pattern = re.escape(term).replace(r"\ /\ ", r"\s*/\s*").replace(r"\ \&\ ", r"\s*&\s*")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", lowered, flags=re.I):
            found.append(term)
    return _prefer_longer_terms(_unique(found))


def _prefer_longer_terms(terms: list[str]) -> list[str]:
    ordered = sorted(terms, key=len, reverse=True)
    kept: list[str] = []
    for term in ordered:
        low = term.lower()
        if any(low in existing.lower() and low != existing.lower() for existing in kept):
            continue
        kept.append(term)
    return sorted(kept, key=lambda item: terms.index(item))


def _find_phase_marked_terms(text: str, terms: list[str], phase_number: int) -> list[str]:
    found: list[str] = []
    phase_pattern = rf"\(?\s*phase\s*{phase_number}\s*\)?"
    for term in terms:
        term_pattern = re.escape(term).replace(r"\ /\ ", r"\s*/\s*").replace(r"\ \&\ ", r"\s*&\s*")
        patterns = [
            rf"{term_pattern}.{{0,40}}{phase_pattern}",
            rf"{phase_pattern}.{{0,80}}{term_pattern}",
        ]
        if any(re.search(pattern, text, flags=re.I | re.S) for pattern in patterns):
            found.append(term)
    return _prefer_longer_terms(_unique(found))


def _collect_scope_terms(chunks: list[EvidenceChunk]) -> dict[str, dict[str, list[str]]]:
    all_text = "\n".join(chunk.text for chunk in chunks)
    result: dict[str, dict[str, list[str]]] = {
        "phase_1": {"products": [], "interfaces": [], "channels": []},
        "phase_2": {"products": [], "interfaces": [], "channels": []},
        "overall": {"products": [], "interfaces": [], "channels": []},
    }
    for group, terms in _SCOPE_TERMS.items():
        result["overall"][group] = _find_terms(all_text, terms)
        for phase in ("phase_1", "phase_2"):
            phase_text = _windowed_text(all_text, phase)
            phase_number = 1 if phase == "phase_1" else 2
            opposite_number = 2 if phase_number == 1 else 1
            marked = _find_phase_marked_terms(all_text, terms, phase_number)
            opposite = set(_find_phase_marked_terms(all_text, terms, opposite_number))
            window_terms = [
                term for term in _find_terms(phase_text, terms)
                if term not in opposite or term in marked
            ]
            result[phase][group] = _prefer_longer_terms(_unique([*marked, *window_terms]))
    return result


def _first_pattern(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return _clean_platform_value(match.group(0))
    return ""


def _clean_platform_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" .,:;")
    if cleaned.lower() == "tdh":
        return "Temenos TDH"
    if cleaned.lower() == "openshift":
        return "Red Hat OpenShift"
    if cleaned.lower() == "not mandatory":
        return "Not mandatory"
    return cleaned


def _release_matches(text: str) -> list[tuple[str, str, int]]:
    patterns = [
        r"\b(?P<component>Transact|T24|Temenos(?:\s+Transact)?)\s+(?:Release|Version)\s+(?P<release>R?\d{2,4}(?:\.\d+)*)\b",
        r"\b(?P<release>R(?:19|20|21|22|23|24|25|26|27|28|29|30))\b\s+(?P<component>Temenos|Transact|T24)\b",
    ]
    matches: list[tuple[str, str, int]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            component = re.sub(r"\s+", " ", match.group("component")).strip()
            release = match.group("release").upper()
            if release.lower() in {"19c", "21c", "23c"}:
                continue
            matches.append((component, release, match.start()))
    return matches


def _context_score(text: str, position: int, want_target: bool) -> float:
    window = text[max(0, position - 280) : min(len(text), position + 360)].lower()
    score = 0.0
    current_terms = ("current", "existing", "as-is", "source", "technology components", "components details")
    target_terms = ("target", "to-be", "upgrade", "future", "r26", "architecture and scope")
    if any(term in window for term in current_terms):
        score += -2.0 if want_target else 3.0
    if any(term in window for term in target_terms):
        score += 3.0 if want_target else -2.0
    if "transact release" in window:
        score += 2.0
    return score


def _extract_stack_detail(text: str, label: str, patterns: list[str], anchor: int) -> str:
    window = text[max(0, anchor - 600) : min(len(text), anchor + 1000)]
    for pattern in patterns:
        match = re.search(pattern, window, flags=re.I)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;")
            return f"{label}: {value}"
    return ""


def _extract_table_value(text: str, field_label: str, stop_labels: list[str], anchor: int) -> str:
    window = text[max(0, anchor - 600) : min(len(text), anchor + 1200)]
    match = re.search(re.escape(field_label), window, flags=re.I)
    if not match:
        return ""
    start = match.end()
    stop_positions = [
        found.start()
        for stop in stop_labels
        if (found := re.search(re.escape(stop), window[start:], flags=re.I))
    ]
    end = start + min(stop_positions) if stop_positions else min(len(window), start + 80)
    value = re.sub(r"\s+", " ", window[start:end]).strip(" .,:;-")
    value = re.sub(r"\bPublic Confidential\b.*$", "", value, flags=re.I).strip(" .,:;-")
    return value


def _version_answer(question: str, chunks: list[EvidenceChunk]) -> str:
    lower = question.lower()
    if not any(term in lower for term in ("version", "release", "r20", "r26", "current temenos", "target temenos")):
        return ""
    all_text = "\n".join(chunk.text for chunk in chunks)
    matches = _release_matches(all_text)
    if not matches:
        return ""

    want_target = any(term in lower for term in ("target", "to-be", "upgrade to", "future"))
    ranked = sorted(
        matches,
        key=lambda item: _context_score(all_text, item[2], want_target),
        reverse=True,
    )
    component, release, position = ranked[0]
    if not want_target and len(ranked) > 1:
        current_ranked = [
            item for item in ranked
            if _context_score(all_text, item[2], want_target=False) >= 0
        ]
        if current_ranked:
            component, release, position = current_ranked[0]

    component_stops = [
        "Transact Runtime",
        "Operating System",
        "Database",
        "User Interface",
        "Java version",
        "Web Application",
        "Public Confidential",
    ]
    runtime = _extract_table_value(all_text, "Transact Runtime", component_stops, position)
    os_value = _extract_table_value(all_text, "Operating System", component_stops, position)
    database = _extract_table_value(
        all_text,
        "Database",
        [label for label in component_stops if label != "Database"],
        position,
    )
    ui = _extract_table_value(all_text, "User Interface", component_stops, position)
    java = _extract_table_value(all_text, "Java version", component_stops, position)
    web_app = _extract_table_value(all_text, "Web Application", component_stops, position)
    details = _unique(
        [
            f"Runtime: {runtime}" if runtime else "",
            f"Operating system: {os_value}" if os_value else "",
            f"Database: {database}" if database else "",
            f"UI: {ui}" if ui else "",
            f"Java: {java}" if java else "",
            f"Web application: {web_app}" if web_app else "",
            _extract_stack_detail(all_text, "Database", [r"Database\s+((?:Oracle\s+)?Database(?:\s+Release\s+Level)?\s+[0-9a-zA-Z.]+)"], position) if not database else "",
        ]
    )
    prefix = "Target" if want_target else "Current"
    base = f"{prefix} Temenos {component} release is {release}."
    if details and ("detail" in lower or "related" in lower or "component" in lower or "stack" in lower):
        return f"{base} Related stack: {'; '.join(details[:6])}."
    if details:
        return f"{base} Related stack includes {'; '.join(details[:3])}."
    return base


def _structured_answer(question: str, chunks: list[EvidenceChunk]) -> str:
    lower = question.lower()
    if not chunks:
        return ""

    version = _version_answer(question, chunks)
    if version:
        return version

    if any(term in lower for term in ("product", "module", "interface", "channel", "phase 1", "phase 2")):
        scope = _collect_scope_terms(chunks)
        wants_phase = "phase 1" in lower or "phase 2" in lower or "compare" in lower
        parts: list[str] = []
        if wants_phase and any(scope["phase_1"].values()):
            p1 = []
            for label in ("products", "interfaces", "channels"):
                values = scope["phase_1"][label]
                if values:
                    p1.append(f"{label}: {', '.join(values[:10])}")
            if p1:
                parts.append(f"Phase 1 has {'; '.join(p1)}.")
        if wants_phase and any(scope["phase_2"].values()):
            p2 = []
            for label in ("products", "interfaces", "channels"):
                values = scope["phase_2"][label]
                if values:
                    p2.append(f"{label}: {', '.join(values[:10])}")
            if p2:
                parts.append(f"Phase 2 has {'; '.join(p2)}.")
        if not parts:
            overall = []
            for label in ("products", "interfaces", "channels"):
                values = scope["overall"][label]
                if values:
                    overall.append(f"{label}: {', '.join(values[:12])}")
            if overall:
                parts.append("; ".join(overall) + ".")
        if parts:
            return _crispify_answer(" ".join(parts), max_words=145, max_sentences=6)

    if any(term in lower for term in ("database", "hosting", "reporting", "container", "platform", "infrastructure")):
        all_text = "\n".join(chunk.text for chunk in chunks)
        values = {
            "database": _first_pattern(all_text, _PLATFORM_PATTERNS["database"]),
            "hosting": _first_pattern(all_text, _PLATFORM_PATTERNS["hosting"]),
            "reporting": _first_pattern(all_text, _PLATFORM_PATTERNS["reporting"]),
            "container": _first_pattern(all_text, _PLATFORM_PATTERNS["container"]),
        }
        if any(values.values()):
            return (
                f"Database: {values['database'] or 'not specified'}. "
                f"Hosting: {values['hosting'] or 'not specified'}. "
                f"Reporting: {values['reporting'] or 'not specified'}. "
                f"Container platform: {values['container'] or 'not specified'}."
            )

    if any(term in lower for term in ("testing", "sit", "uat", "implementation stages", "methodology", "stage")):
        all_text = "\n".join(chunk.text for chunk in chunks)
        facts = []
        if re.search(r"\bTIM\b|Temenos Implementation Methodology", all_text, flags=re.I):
            facts.append("TIM methodology")
        if re.search(r"pre[- ]contract\s+scoping|scoping\s+and\s+sizing", all_text, flags=re.I):
            facts.append("pre-contract scoping and sizing")
        if re.search(r"project\s+closure", all_text, flags=re.I):
            facts.append("project closure")
        if re.search(r"post[- ]implementation\s+review", all_text, flags=re.I):
            facts.append("post-implementation review")
        if re.search(r"project\s+kick[- ]off|initiation", all_text, flags=re.I):
            facts.append("initiation/kick-off")
        if re.search(r"\b(system analysis|analysis phase)\b", all_text, flags=re.I):
            facts.append("system analysis")
        if re.search(r"\b(build phase|configuration|development)\b", all_text, flags=re.I):
            facts.append("build/configuration")
        if re.search(r"\bSIT\b|System\s+Integr\s*ation\s+Testing|System Integration Testing", all_text, flags=re.I):
            facts.append("SIT")
        if re.search(r"\bUAT\b|User\s+Acceptance\s+Testing", all_text, flags=re.I):
            facts.append("UAT")
        if re.search(r"\btraining\b", all_text, flags=re.I):
            facts.append("training")
        if re.search(r"\b(go[- ]live|cutover)\b", all_text, flags=re.I):
            facts.append("go-live/cutover")
        if facts:
            clarification = "Clarify ownership, entry/exit criteria, test cycles, environments, deliverables, and sign-off responsibilities."
            return f"Implementation flow covers {', '.join(_unique(facts))}. {clarification}"

    return ""


def _split_subquestions(question: str) -> list[str]:
    """Build focused retrieval probes without trusting the model to plan."""
    cleaned = re.sub(r"\s+", " ", question.strip())
    if not cleaned:
        return []

    candidates = [cleaned]
    for part in re.split(r"[;\n]|\?\s+", cleaned):
        if part and part.lower() != cleaned.lower():
            candidates.append(part)

    lower = cleaned.lower()
    if re.search(r"\bphase\s*1\b", lower):
        candidates.append("phase 1 scope products channels regulatory interfaces implementation plan")
    if re.search(r"\bphase\s*2\b", lower):
        candidates.append("phase 2 scope products channels regulatory interfaces implementation plan")
    if any(term in lower for term in ("compare", "difference", "versus", " vs ")):
        candidates.append("comparison differences scope phases products channels interfaces")
    if any(term in lower for term in ("database", "hosting", "infrastructure", "reporting", "volume")):
        candidates.append("database hosting infrastructure reporting platform customer volume targets")
    if any(term in lower for term in ("methodology", "approach", "timeline", "stages", "workstream")):
        candidates.append("implementation methodology approach stages workstreams timeline")
    if any(term in lower for term in ("version", "upgrade", "current", "target")):
        candidates.append("current version target version upgrade scope migration")

    return _unique(candidates)[:6]


def _sentence_split(text: str) -> list[str]:
    normalized = text or ""
    normalized = re.sub(r"(?i)\b(months?\s+\d+(?:[-–]\d+)?)\b", r". \1", normalized)
    normalized = re.sub(r"(?i)\b(phase\s+\d+\s*[:\-–])", r". \1", normalized)
    normalized = re.sub(r"(?i)\b(year\s+\d+\s*[:\-–])", r". \1", normalized)
    normalized = re.sub(r"[\r\n]+", ". ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return []
    pieces = re.split(r"(?<=[.!?])\s+|(?:\s+-\s+)|(?:\s+\|\s+)", normalized)
    return [piece.strip(" -") for piece in pieces if len(piece.strip()) > 12]


def _sentence_score(question: str, sentence: str) -> float:
    terms = set(_query_terms(question))
    sentence_terms = set(_query_terms(sentence))
    if not sentence_terms:
        return 0.0
    score = 0.0
    score += 2.0 * len(terms & sentence_terms)
    lower_question = question.lower()
    lower_sentence = sentence.lower()
    for phrase in ("phase 1", "phase 2", "year 1", "year 2", "year 3", "big bang", "mvp"):
        if phrase in lower_question and phrase in lower_sentence:
            score += 3.0
    if re.search(r"\b(version|volume|date|timeline|duration|how many|number|target)\b", lower_question):
        if re.search(r"\d", sentence):
            score += 2.0
    if re.search(r"\b(product|module|channel|interface|database|hosting|reporting)\b", lower_question):
        if re.search(r"\b(product|module|channel|interface|database|hosting|reporting|analytics|iris|transact)\b", lower_sentence):
            score += 1.5
    if re.search(r"\b(what|which|list|show|summarize|summarise|detail|scope|include)\b", lower_question):
        if re.search(r"\b(phase|module|product|interface|channel|version|database|oracle|aws|sit|uat|migration|training|go-live|timeline)\b", lower_sentence):
            score += 2.0
    return score


def _best_sentences(question: str, text: str, max_sentences: int = 2) -> list[str]:
    sentences = _sentence_split(text)
    if not sentences:
        return []
    ranked = sorted(
        ((sentence, _sentence_score(question, sentence)) for sentence in sentences),
        key=lambda item: item[1],
        reverse=True,
    )
    selected = [sentence for sentence, score in ranked if score > 0][:max_sentences]
    if not selected:
        selected = sentences[:max_sentences]
    return [_trim_fact(sentence) for sentence in selected]


def _trim_fact(sentence: str, max_words: int = 34) -> str:
    cleaned = re.sub(r"\s+", " ", sentence).strip(" .;:-")
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned
    trimmed = " ".join(words[:max_words]).rstrip(",;:-")
    return f"{trimmed}..."


def _answer_shape(question: str) -> str:
    lower = question.lower()
    if any(term in lower for term in ("compare", "difference", "phase 1", "phase 2", "versus", " vs ")):
        return "Use 2-4 short bullets or compact sentences grouped by compared item."
    if any(term in lower for term in ("list", "which", "what are", "modules", "products", "interfaces", "channels")):
        return "Use a concise grouped list with the exact detected names."
    if any(term in lower for term in ("why", "risk", "impact", "clarify", "next step")):
        return "Use concise advisory prose tied to the evidence facts."
    return "Use 2-4 precise sentences."


def _specificity_rules(question: str) -> list[str]:
    lower = question.lower()
    rules = [
        "Prefer specific names, counts, dates, phases, versions, products, modules, systems, and interfaces.",
        "Do not replace specific evidence with broad phrases such as 'core banking capabilities' or 'digital channels' if names are available.",
    ]
    if "phase" in lower:
        rules.append("Separate Phase 1, Phase 2, and later-phase scope if the evidence supports it.")
    if any(term in lower for term in ("database", "hosting", "infrastructure", "platform")):
        rules.append("Name the exact database, hosting model, container platform, reporting platform, and unknown items separately.")
    if any(term in lower for term in ("module", "product", "interface", "channel")):
        rules.append("Return exact module/product/interface/channel names instead of category summaries.")
    if any(term in lower for term in ("current", "target", "upgrade", "version")):
        rules.append("Distinguish current state from target state; do not mix them.")
    return rules


def _filter_by_documents(
    chunks: list[EvidenceChunk], document_names: list[str]
) -> list[EvidenceChunk]:
    if not document_names:
        return chunks
    wanted = {name.strip().lower() for name in document_names if name.strip()}
    if not wanted:
        return chunks
    filtered = []
    for chunk in chunks:
        haystack = " ".join(
            [
                chunk.source_document or "",
                chunk.source_proposal or "",
                chunk.summary or "",
                chunk.text or "",
            ]
        ).lower()
        if any(name in haystack for name in wanted):
            filtered.append(chunk)
    return filtered


def _lexical_rank(
    query: str,
    payloads: list[dict[str, str]],
    document_names: list[str],
) -> list[EvidenceChunk]:
    query_terms = set(_tokens(query))
    if not query_terms:
        return []

    docs: list[tuple[dict[str, str], list[str], str]] = []
    wanted = {name.lower() for name in document_names if name.strip()}
    for payload in payloads:
        norm = {
            "text": payload.get("text", ""),
            "summary": payload.get("chunk_summary", ""),
            "source": payload.get("source_proposal", ""),
            "section": payload.get("source_section", ""),
            "document": payload.get("document_name", "") or payload.get("file", ""),
            "family": payload.get("proposal_family", ""),
            "chunk_id": payload.get("_point_id", ""),
        }
        haystack = " ".join(
            [norm["text"], norm["summary"], norm["source"], norm["section"], norm["document"], norm["family"]]
        ).lower()
        if wanted and not any(name in haystack for name in wanted):
            continue
        tokens = _tokens(haystack)
        if not tokens or not (query_terms & set(tokens)):
            continue
        docs.append((norm, tokens, haystack))

    if not docs:
        return []

    avgdl = sum(len(tokens) for _norm, tokens, _haystack in docs) / max(len(docs), 1)
    df = Counter()
    for _norm, tokens, _haystack in docs:
        df.update(set(tokens))

    scored: list[tuple[float, EvidenceChunk]] = []
    k1 = 1.4
    b = 0.72
    for norm, tokens, haystack in docs:
        counts = Counter(tokens)
        score = 0.0
        for term in query_terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (len(docs) - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            denom = tf + k1 * (1 - b + b * (len(tokens) / max(avgdl, 1)))
            score += idf * ((tf * (k1 + 1)) / denom)
        if norm["document"] and norm["document"].lower() in query.lower():
            score += 2.0
        if norm["section"] and norm["section"].lower() in query.lower():
            score += 1.0
        scored.append(
            (
                score,
                EvidenceChunk(
                    text=norm["text"],
                    summary=norm["summary"] or " ".join(norm["text"].split()[:12]),
                    score=score,
                    source_proposal=norm["source"],
                    source_section=norm["section"],
                    source_document=norm["document"],
                    proposal_family=norm["family"],
                    chunk_id=norm["chunk_id"],
                    source_type="document_bm25",
                ),
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _score, chunk in scored]


def _relevance_score(query: str, chunk: EvidenceChunk) -> float:
    terms = set(_query_terms(query))
    haystack = " ".join(
        [
            chunk.text or "",
            chunk.summary or "",
            chunk.source_section or "",
            chunk.source_document or "",
            chunk.source_proposal or "",
        ]
    )
    haystack_terms = set(_query_terms(haystack))
    score = float(chunk.score or 0.0)
    if terms and haystack_terms:
        score += 2.5 * len(terms & haystack_terms) / max(len(terms), 1)
    lower_query = query.lower()
    lower_haystack = haystack.lower()
    for phrase in ("phase 1", "phase 2", "year 1", "year 2", "year 3", "mvp", "big bang"):
        if phrase in lower_query and phrase in lower_haystack:
            score += 1.5
    if chunk.source_document and chunk.source_document.lower() in lower_query:
        score += 2.0
    if chunk.source_section and chunk.source_section.lower() in lower_query:
        score += 1.0
    if re.search(r"\b(version|volume|date|timeline|duration|number|target)\b", lower_query):
        if re.search(r"\d", chunk.text or ""):
            score += 0.8
    return score


def _retrieve_candidates(
    *,
    qdrant,
    settings,
    query: str,
    payloads: list[dict[str, str]],
    document_names: list[str],
    top_k: int,
) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    try:
        if settings.embedding_provider.strip().lower() == "qdrant":
            chunks = qdrant.search_text(query, model=settings.embedding_model, top_k=max(top_k * 3, 18))
        else:
            vector = get_embedder().embed_query(query)
            chunks = qdrant.search(vector, top_k=max(top_k * 3, 18))
    except Exception:
        chunks = []

    lexical = _lexical_rank(query, payloads, document_names)
    merged: dict[str, EvidenceChunk] = {}
    for chunk in [*chunks, *lexical[: max(top_k * 3, 18)]]:
        key = chunk.chunk_id or f"{chunk.source_document}:{chunk.summary}:{chunk.text[:80]}"
        score = _relevance_score(query, chunk)
        chunk.score = score
        if key in merged:
            merged[key].score = max(merged[key].score, score) + 0.2
        else:
            merged[key] = chunk
    ranked = _filter_by_documents(list(merged.values()), document_names)
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[: max(top_k * 3, 18)]


def _mmr_select(chunks: list[EvidenceChunk], top_k: int) -> list[EvidenceChunk]:
    if len(chunks) <= top_k:
        return chunks
    selected: list[EvidenceChunk] = [chunks[0]]
    remaining = chunks[1:]
    while remaining and len(selected) < top_k:
        best_idx = 0
        best_score = float("-inf")
        for idx, chunk in enumerate(remaining):
            relevance = chunk.score
            diversity_penalty = 0.0
            chunk_terms = set(_tokens(chunk.text))
            for chosen in selected:
                chosen_terms = set(_tokens(chosen.text))
                if not chunk_terms or not chosen_terms:
                    continue
                overlap = len(chunk_terms & chosen_terms) / max(len(chunk_terms | chosen_terms), 1)
                diversity_penalty = max(diversity_penalty, overlap)
            mmr = 0.75 * relevance - 0.25 * diversity_penalty
            if mmr > best_score:
                best_score = mmr
                best_idx = idx
        selected.append(remaining.pop(best_idx))
    return selected


def _crispify_answer(answer: str, max_words: int = 80, max_sentences: int = 4) -> str:
    cleaned = re.sub(r"\s+", " ", (answer or "").strip())
    cleaned = re.sub(
        r"^(?:retrieved evidence|evidence|answer|summary)\s*[:\-]\s*",
        "",
        cleaned,
        flags=re.I,
    )
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    cleaned = " ".join(sentences[:max_sentences]).strip()
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(",;:-")
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _fallback_answer(question: str, chunks: list[EvidenceChunk], subquestions: list[str]) -> str:
    if not chunks:
        return "No retrieved evidence was available."
    probes = subquestions or [question]
    facts: list[str] = []
    for probe in probes[:4]:
        for chunk in chunks:
            for sentence in _best_sentences(probe, chunk.text, max_sentences=1):
                if sentence not in facts:
                    facts.append(sentence)
                    break
            if len(facts) >= len(probes[:4]):
                break
    if not facts:
        facts = _best_sentences(question, chunks[0].text, max_sentences=2)
    return _crispify_answer(" ".join(facts), max_words=90, max_sentences=4)


def _dedupe_chunks(chunks: Iterable[EvidenceChunk]) -> list[EvidenceChunk]:
    seen: set[str] = set()
    deduped: list[EvidenceChunk] = []
    for chunk in chunks:
        key = chunk.chunk_id or f"{chunk.source_document}:{chunk.summary}:{chunk.text[:60]}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


async def answer_document_query(
    question: str,
    history: list[ChatMessage] | None = None,
    document_names: list[str] | None = None,
    model: str | None = None,
    top_k: int = 8,
) -> DocumentQueryResponse:
    settings = get_settings()
    qdrant = get_qdrant()
    history = history or []
    document_names = document_names or []

    query = question.strip()
    if history:
        recent = [msg.content.strip() for msg in history[-4:] if msg.content.strip()]
        if recent:
            query = "\n".join([*recent, question.strip()])

    subquestions = _split_subquestions(question)
    retrieval_queries = _unique([query, question, *subquestions])
    payloads = qdrant.scroll_payloads(limit=5000)

    merged: dict[str, EvidenceChunk] = {}
    for idx, retrieval_query in enumerate(retrieval_queries):
        candidates = _retrieve_candidates(
            qdrant=qdrant,
            settings=settings,
            query=retrieval_query,
            payloads=payloads,
            document_names=document_names,
            top_k=top_k,
        )
        query_boost = max(0.0, 0.45 - (idx * 0.06))
        for chunk in candidates:
            key = chunk.chunk_id or f"{chunk.source_document}:{chunk.summary}:{chunk.text[:80]}"
            chunk.score = _relevance_score(question, chunk) + query_boost
            if key in merged:
                existing = merged[key]
                existing.score = max(existing.score, chunk.score) + 0.2
            else:
                merged[key] = chunk

    if not merged:
        fallback_candidates = _lexical_rank(question, payloads, document_names)[: max(top_k * 2, 12)]
        for chunk in fallback_candidates:
            key = chunk.chunk_id or f"{chunk.source_document}:{chunk.summary}:{chunk.text[:80]}"
            chunk.score = _relevance_score(question, chunk)
            merged[key] = chunk

    chunks = _filter_by_documents(_dedupe_chunks(list(merged.values())), document_names)
    chunks.sort(key=lambda item: item.score, reverse=True)
    chunks = _mmr_select(chunks, max(top_k, 8))

    # Re-rank after MMR because diversity can pull in weak chunks for multi-part questions.
    for chunk in chunks:
        chunk.score = _relevance_score(question, chunk)
    chunks.sort(key=lambda item: item.score, reverse=True)
    chunks = chunks[: max(top_k, 8)]

    evidence_chunks = chunks[:top_k]

    used_documents = list(
        OrderedDict.fromkeys(
            [
                doc
                for doc in (
                    chunk.source_document or chunk.source_proposal or ""
                    for chunk in evidence_chunks
                )
                if doc
            ]
        )
    )

    fact_lines: list[str] = []
    for idx, chunk in enumerate(chunks, 1):
        facts = _best_sentences(question, chunk.text, max_sentences=2)
        if not facts:
            continue
        fact_lines.append(
            f"[{idx}] Document: {chunk.source_document or chunk.source_proposal or 'unknown'} | "
            f"Section: {chunk.source_section or chunk.summary or 'unknown'} | "
            f"Facts: {' '.join(facts)}"
        )

    evidence_block = "\n".join(fact_lines[: max(top_k, 8)])

    multi_step = len(subquestions) > 2 or bool(
        re.search(r"\b(compare|and|versus| vs |phase\s*1.*phase\s*2|database.*hosting)\b", question, re.I)
    )
    max_answer_words = 150 if multi_step else 95
    max_answer_sentences = 6 if multi_step else 4
    answer_shape = _answer_shape(question)
    specificity_rules = "\n".join(f"- {rule}" for rule in _specificity_rules(question))
    structured = _structured_answer(question, chunks)

    system = (
        "You answer questions about uploaded proposal documents. Use ONLY the "
        "provided compact evidence facts. Do not use outside knowledge, memory, "
        "or hidden reasoning. Your job is not to summarize the whole document; "
        "answer the user's exact question using the most specific supported facts. "
        "Never paste raw chunks, source labels, or evidence IDs. Return strict JSON only."
    )
    user = f"""Return STRICT JSON only in this exact shape:
{{"answer":"..."}}

Question:
{question}

Focused retrieval probes:
{chr(10).join(f"- {item}" for item in subquestions) or "- none"}

Compact evidence facts:
{evidence_block or '(no evidence retrieved)'}

Rules:
- Use only the evidence facts above.
- Answer the exact question, including each requested part.
- Answer format: {answer_shape}
- Specificity requirements:
{specificity_rules}
- Keep the answer under {max_answer_words} words.
- Do not say "chunk", "evidence", "retrieved", "based on", or cite document names in the answer.
- If evidence is insufficient, say exactly what is missing in one sentence."""

    answer = ""
    try:
        if evidence_block:
            raw_answer = await get_llm().chat_json(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                model=model,
                temperature=0.0,
                max_tokens=420,
            )
            if isinstance(raw_answer, dict):
                answer = str(raw_answer.get("answer", "")).strip()
            else:
                answer = str(raw_answer).strip()
    except LLMError:
        answer = ""

    fallback = _fallback_answer(question, chunks, subquestions)
    if structured:
        answer = structured
    if not answer:
        answer = fallback

    answer = _crispify_answer(
        answer,
        max_words=max_answer_words,
        max_sentences=max_answer_sentences,
    )
    bad_patterns = [
        r"\[\d+\]",
        r"retrieved evidence",
        r"evidence block",
        r"\bchunk\b",
        r"\bsource\b",
        r"\bdocument:\b",
        r"(?:month\s+\d+.*){3,}",
        r"(?:months\s+\d+.*){2,}",
    ]
    if (
        len(answer.split()) > max_answer_words
        or any(re.search(pattern, answer, flags=re.I) for pattern in bad_patterns)
    ):
        answer = fallback

    return DocumentQueryResponse(answer=answer.strip(), evidence=evidence_chunks, used_documents=used_documents)
