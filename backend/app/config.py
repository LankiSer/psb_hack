import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def disable_local_proxies() -> None:
    """Системный HTTP proxy на Windows даёт 503 на localhost (Ollama/Qdrant)."""
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


disable_local_proxies()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:4b"
    ollama_num_ctx: int = 8192
    ollama_keep_alive: str = "15m"
    ollama_embed_model: str = "nomic-embed-text"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_npa: str = "npa"
    qdrant_collection_practice: str = "practice"

    data_dir: str = "./data"
    request_timeout_sec: int = 60

    # Auth
    jwt_secret: str = "change-me-in-production-ai-docs"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # Файлы
    max_upload_bytes: int = 25 * 1024 * 1024
    allowed_mime_types: str = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/msword,"
        "application/pdf,"
        "text/plain,"
        "text/markdown,"
        "application/rtf,"
        "application/vnd.oasis.opendocument.text,"
        "application/json"
    )

    # OnlyOffice
    onlyoffice_api_url: str = "http://host.docker.internal:8000"
    onlyoffice_url: str = "http://localhost:8080"
    onlyoffice_jwt_secret: str = "onlyoffice-jwt-secret-change-me"
    public_api_url: str = "http://localhost:8000"

    # Redis / Kafka (отказоустойчивость)
    redis_url: str = "redis://127.0.0.1:6380/0"
    redis_cache_ttl_sec: int = 300
    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "127.0.0.1:9094"
    kafka_consumer_group: str = "ai-docs-workers"

    # Масштаб ingest судебной практики
    sudact_limit_per_query: int = 10
    sudact_pages: int = 2
    sudact_fetch_full_text: bool = True
    sudact_max_full_docs: int = 50

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).resolve()

    @property
    def seed_path(self) -> Path:
        return self.data_path / "seed"

    @property
    def raw_npa_path(self) -> Path:
        return self.data_path / "raw" / "npa"

    @property
    def raw_practice_path(self) -> Path:
        return self.data_path / "raw" / "practice"

    @property
    def sqlite_path(self) -> Path:
        return self.data_path / "app.db"

    @property
    def files_path(self) -> Path:
        return self.data_path / "files"

    @property
    def allowed_mimes(self) -> set[str]:
        return {item.strip() for item in self.allowed_mime_types.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
