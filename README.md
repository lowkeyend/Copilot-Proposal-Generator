# Proposal Copilot

Generate client-ready proposals from an existing proposal knowledge base.
This repo is now local-first: you can clone it on another laptop and run it on
`localhost` without Railway or Vercel.

The app includes:
- section-by-section proposal generation
- evidence drawer for retrieved chunks
- knowledge base browser/editor/deleter
- Temenos-specific grounding from official product summaries
- local fallback generation when OpenRouter is not configured

## Local setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Git

No external API key is required for the local fallback mode.
If you add `OPENROUTER_API_KEY`, the app will use it for richer generation.

### Start everything on localhost

From the repo root:

```powershell
.\run_local.ps1
```

That script starts:
- backend on `http://localhost:8000`
- frontend on `http://localhost:3000`

If you prefer separate terminals:

```powershell
.\run_backend.ps1
.\run_frontend.ps1
```

The first run will create:
- `backend/.env` from `backend/.env.example`
- `frontend/.env.local` from `frontend/.env.local.example`

So a fresh clone does not need manual env setup for local development.

## How it works

1. Page 1 extracts context and proposal family from your prompt.
2. Page 2 builds a TOC.
3. Each section is written one at a time.
4. Retrieval tries Qdrant first.
5. If embeddings are unavailable, the backend falls back to lexical matching
   and Temenos official knowledge summaries.
6. If OpenRouter is not configured, the section writer falls back to a local
   evidence-grounded writer so generation still works.

## Knowledge base

- The app reads from the existing Qdrant collection `proposal_knowledge_base`.
- Use the Knowledge Base tab in the workspace to inspect, edit, and delete
  chunks.
- Deleting a chunk removes it from Qdrant.

## Files you should know

- `backend/app/main.py` - FastAPI entrypoint and CORS
- `backend/app/agents/retrieval_agent.py` - evidence retrieval
- `backend/app/agents/section_writer.py` - section generation
- `backend/app/services/qdrant_service.py` - Qdrant read/update/delete
- `frontend/app/workspace/page.tsx` - proposal workspace
- `frontend/app/knowledge-base/page.tsx` - chunk browser/editor

## Optional cloud deployment

Cloud deployment is still supported, but it is optional. If you want to use
Railway/Vercel later, update env vars instead of changing code.

