"""Agent 1 — Client Context Agent.

Turns a free-text request into structured client context. Form-field hints
from Page 1 (client name / industry / project type) take priority over the
model's inference so the user's explicit input is never overridden.
"""

from __future__ import annotations

from typing import Optional

from app.models.schemas import ClientContext, GenerateContextRequest
from app.services.llm_service import LLMError, get_llm

_SYSTEM = (
    "You are a proposal intake analyst. Extract structured client context "
    "from a sales/bid request. Respond with STRICT JSON only, no prose."
)

_TEMPLATE = """Extract the following fields from the request below.

Return JSON exactly in this shape:
{{
  "client_name": "",
  "industry": "",
  "project_type": "",
  "tone": "",
  "special_instructions": ""
}}

Rules:
- client_name: the organisation the proposal is for.
- industry: their sector (e.g. Banking, Insurance, Government).
- project_type: the work/solution (e.g. Temenos implementation, Cloud migration).
- tone: writing tone requested (default "Formal" if unspecified).
- special_instructions: any emphasis, constraints, or must-haves mentioned.
- Use empty string if genuinely unknown. Do not invent a client name.

REQUEST:
\"\"\"{prompt}\"\"\"
"""


async def run_context_agent(req: GenerateContextRequest) -> ClientContext:
    llm = get_llm()
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _TEMPLATE.format(prompt=req.prompt)},
            ],
            model=req.model,
        )
    except LLMError:
        data = {}

    ctx = ClientContext(
        client_name=_clean(data.get("client_name")),
        industry=_clean(data.get("industry")),
        project_type=_clean(data.get("project_type")),
        tone=_clean(data.get("tone")) or "Formal",
        special_instructions=_clean(data.get("special_instructions")),
    )

    # Explicit form hints win.
    if req.client_name:
        ctx.client_name = req.client_name
    if req.industry:
        ctx.industry = req.industry
    if req.project_type:
        ctx.project_type = req.project_type
    return ctx


def _clean(value: Optional[str]) -> str:
    if not value:
        return ""
    return str(value).strip()
