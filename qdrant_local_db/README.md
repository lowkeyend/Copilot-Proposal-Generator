# Place your existing Qdrant DB here

This folder is where the backend expects the **on-disk Qdrant database created
by Notebook 1** (the ingestion notebook).

- Collection name: `proposal_knowledge_base`
- Embedding model: `BAAI/bge-large-en-v1.5`

Copy the contents of your Notebook-1 `qdrant_local_db` directory into this
folder (you should see Qdrant's internal files such as `collection/`,
`meta.json`, etc.).

The backend reads this via `QDRANT_PATH` in `backend/.env` (default
`../qdrant_local_db`). To use Qdrant Cloud instead, set `QDRANT_URL` +
`QDRANT_API_KEY` and this folder is ignored.

> Ingestion / embedding / population is **never** rebuilt by this application —
> it treats Qdrant strictly as a read-only knowledge base.
