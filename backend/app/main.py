"""Proposal Copilot - FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.services.runtime_settings_service import set_request_openrouter_api_key

settings = get_settings()

app = FastAPI(
    title="Proposal Copilot API",
    version="1.0.0",
    description="Generate professional proposals from an existing proposal knowledge base.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_pattern or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def capture_openrouter_key(request: Request, call_next):
    set_request_openrouter_api_key(request.headers.get("x-openrouter-api-key", ""))
    try:
        return await call_next(request)
    finally:
        set_request_openrouter_api_key("")


app.include_router(router)

# Serve generated DOCX files for download.
app.mount(
    "/files",
    StaticFiles(directory=str(settings.generated_path)),
    name="files",
)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Proposal Copilot API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
