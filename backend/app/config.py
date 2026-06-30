"""Central configuration layer.

Everything that differs between localhost and a cloud deployment
(Qdrant, storage, LLM endpoint, CORS) is funnelled through this single
`Settings` object so the rest of the code never hardcodes an environment.
Switching from local Qdrant -> Qdrant Cloud, or local storage -> Supabase,
is a matter of changing env vars, not code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = proposal-copilot/ (two levels up from this file:
# backend/app/config.py -> backend/ -> proposal-copilot/)
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM ----
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    default_model: str = Field(
        default="openrouter/free",
        alias="DEFAULT_MODEL",
    )
    openrouter_app_url: str = Field(
        default="http://localhost:3000", alias="OPENROUTER_APP_URL"
    )
    openrouter_app_name: str = Field(
        default="Proposal Copilot", alias="OPENROUTER_APP_NAME"
    )

    # ---- Qdrant ----
    qdrant_path: str = Field(default="../qdrant_local_db", alias="QDRANT_PATH")
    qdrant_url: str = Field(default="", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="proposal_knowledge_base_v3", alias="QDRANT_COLLECTION"
    )

    # ---- Embeddings ----
    embedding_provider: str = Field(default="qdrant", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL"
    )
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_api_base_url: str = Field(
        default="", alias="EMBEDDING_API_BASE_URL"
    )
    embedding_query_prefix: str = Field(
        default="Represent this sentence for searching relevant passages:",
        alias="EMBEDDING_QUERY_PREFIX",
    )

    # ---- Storage ----
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    storage_dir: str = Field(default="../storage", alias="STORAGE_DIR")
    generated_dir: str = Field(default="../generated", alias="GENERATED_DIR")
    templates_dir: str = Field(default="../templates", alias="TEMPLATES_DIR")
    assets_dir: str = Field(default="../assets", alias="ASSETS_DIR")

    # ---- Server ----
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS"
    )
    cors_origin_regex: str = Field(
        default=r"https://.*\.vercel\.app$", alias="CORS_ORIGIN_REGEX"
    )

    # ---- Supported models exposed to the UI ----
    supported_models: list[str] = [
        "openrouter/free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "deepseek/deepseek-chat-v3.1:free",
        "qwen/qwen3-32b",
        "deepseek/deepseek-chat",
    ]

    # ---------- Derived helpers ----------
    def _resolve(self, value: str) -> Path:
        """Resolve a possibly-relative path against the backend/ directory."""
        p = Path(value)
        if not p.is_absolute():
            p = (Path(__file__).resolve().parents[1] / p).resolve()
        return p

    @property
    def storage_path(self) -> Path:
        return self._resolve(self.storage_dir)

    @property
    def generated_path(self) -> Path:
        return self._resolve(self.generated_dir)

    @property
    def templates_path(self) -> Path:
        return self._resolve(self.templates_dir)

    @property
    def assets_path(self) -> Path:
        return self._resolve(self.assets_dir)

    @property
    def qdrant_local_path(self) -> Path:
        return self._resolve(self.qdrant_path)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_origin_pattern(self) -> str:
        return self.cors_origin_regex.strip()

    @property
    def use_qdrant_cloud(self) -> bool:
        return bool(self.qdrant_url.strip())

    @property
    def use_hosted_embeddings(self) -> bool:
        return self.embedding_provider.strip().lower() in {
            "openai",
            "hosted",
            "jina",
            "qdrant",
        }

    @property
    def embedding_api_root(self) -> str:
        explicit = self.embedding_api_base_url.strip()
        if explicit:
            return explicit
        provider = self.embedding_provider.strip().lower()
        if provider == "jina":
            return "https://api.jina.ai/v1"
        return "https://api.openai.com/v1"

    def ensure_dirs(self) -> None:
        for p in (
            self.storage_path,
            self.storage_path / "proposals",
            self.generated_path,
            self.templates_path,
            self.assets_path,
        ):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
