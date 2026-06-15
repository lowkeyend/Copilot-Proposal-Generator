"""Proposal Copilot — FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api.routes import router

settings = get_settings()

app = FastAPI(
    title="Proposal Copilot API",
    version="1.0.0",
    description="Generate professional proposals from an existing proposal knowledge base.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
