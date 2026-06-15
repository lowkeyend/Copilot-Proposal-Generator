# Proposal Copilot

Generate professional, client-ready proposals from your **existing proposal
knowledge base**. The platform learns patterns from previously uploaded
proposals, retrieves relevant content, builds an editable plan, writes each
section with an LLM, lets you review/edit/regenerate/lock sections in a
workspace, shows the evidence behind every section, and exports a branded DOCX.

> **Local-first, cloud-ready.** Everything runs on `localhost` with zero cloud
> dependencies except the LLM. The config layer is built so you can later move
> to Qdrant Cloud, Supabase, Railway, and Vercel by changing env vars only.

---

## Architecture

```
proposal-copilot/
├── backend/            FastAPI + agents + services
│   └── app/
│       ├── api/        HTTP routes
│       ├── agents/     9 agents (context → classify → patterns → TOC → retrieve → write → review)
│       ├── services/   Qdrant, embeddings, LLM (OpenRouter), storage, DOCX
│       ├── models/     Pydantic schemas
│       └── utils/
├── frontend/           Next.js + TypeScript + Tailwind + Framer Motion
├── generated/          Exported .docx files
├── storage/            Saved proposals, versions, templates, pattern_registry.json
├── templates/          (reserved for branded .docx templates / assets)
├── assets/             Logos / brand assets
└── qdrant_local_db/    ← your existing Qdrant DB from Notebook 1 goes here
```

### Agents

| # | Agent | Role |
|---|-------|------|
| 1 | Client Context | Prompt → structured `{client, industry, project_type, tone, instructions}` |
| 2 | Proposal Classifier | Detects the proposal *family* (prompt + KB signals) |
| 3 | Pattern Discovery | **Learns** section patterns from the corpus → `pattern_registry.json` |
| 4 | Template Suggestion | Suggests best-fit pattern; user can accept/modify |
| 5 | Dynamic TOC Builder | Editable outline = the generation plan |
| 6 | Retrieval | Per-section, metadata-aware chunk retrieval from Qdrant |
| 7 | Section Writer | Writes each section **one at a time**, grounded in evidence |
| 8 | Consistency Reviewer | Client/project/terminology/tone/coherence checks |
| 9 | DOCX Composer | Branded DOCX: TOC field, headings, tables, headers/footers, page numbers |

---

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- An **OpenRouter API key** (https://openrouter.ai/keys)
- Your **existing Qdrant DB** from Notebook 1 (collection `proposal_knowledge_base`).
  Copy/point it into `qdrant_local_db/`. *Ingestion is never rebuilt by this app.*

> The app runs even **without** the Qdrant DB attached — it falls back to seed
> patterns and writes sections from best practice, so you can demo the full UI
> immediately. Attach the DB to light up retrieval + evidence.

---

## Quick start

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env              # macOS/Linux: cp .env.example .env
# edit .env -> set OPENROUTER_API_KEY
python -m app.main                  # serves http://localhost:8000  (docs at /docs)
```

### 2. Frontend

```powershell
cd frontend
npm install
copy .env.local.example .env.local  # macOS/Linux: cp ...
npm run dev                         # http://localhost:3000
```

Open **http://localhost:3000**, fill in the request, and click **Generate Proposal**.

Helper scripts at the repo root: `run_backend.ps1`, `run_frontend.ps1`.

---

## Using it

1. **Setup (Page 1)** — enter client/industry/project, a natural-language
   prompt, pick a model (`deepseek/deepseek-chat` or `qwen/qwen3-32b`), and
   generate. The system extracts context, classifies the family, suggests a
   discovered pattern, and builds an editable TOC.
2. **Workspace (Page 2)** — edit the TOC (add/rename/reorder/remove), then
   generate section-by-section with live progress. Each **section card** can be
   edited, regenerated (with an instruction like *"make it shorter"*), locked,
   deleted, and reordered. The **evidence drawer** shows the exact chunks +
   source proposal/section behind each section.
3. **Review** — run the consistency reviewer.
4. **Versions** — every generation/save creates a restorable version.
5. **Export** — download a branded DOCX.

---

## API endpoints

`POST /generate-context` · `POST /suggest-template` · `POST /build-toc` ·
`POST /generate-section` · `POST /generate-proposal` · `POST /regenerate-section` ·
`POST /review-proposal` · `POST /export-docx` · `GET /templates` · `GET /versions`

Plus utilities: `GET /status`, `GET /models`, `GET /patterns`,
`POST /discover-patterns`, template CRUD, proposal/version reads, `/files/*` downloads.
Full interactive docs at **http://localhost:8000/docs**.

---

## Future deployment (no code changes, env only)

| Local | Cloud | How |
|-------|-------|-----|
| Local Qdrant | Qdrant Cloud | set `QDRANT_URL` + `QDRANT_API_KEY` |
| Local storage | Supabase | implement the `StorageService` interface for Supabase |
| FastAPI | Railway | deploy `backend/`, set env vars |
| Next.js | Vercel | deploy `frontend/`, set `NEXT_PUBLIC_API_BASE` |

No `localhost` is hardcoded — see `backend/app/config.py` and
`frontend/lib/api.ts`.
