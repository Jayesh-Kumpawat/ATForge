from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    db_path: Path = Field(default=REPO_ROOT / "data" / "atforge.db", alias="ATFORGE_DB_PATH")
    cache_dir: Path = Field(default=REPO_ROOT / "data" / "cache", alias="ATFORGE_CACHE_DIR")

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    google_api_key: str | None = None
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None
    cerebras_api_key: str | None = None
    nvidia_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    enable_ollama: bool = False
    llm_default_model: str = "gemini-2.5-flash"
    llm_provider_priority: list[str] = Field(
        default_factory=lambda: ["gemini", "groq", "openrouter", "cerebras", "nvidia"]
    )

    qdrant_url: str | None = None
    qdrant_api_key: str | None = None

    # Ratchet thresholds (override via env or .env)
    ratchet_min_delta_sharpe: float = 0.05
    ratchet_min_delta_sortino: float = 0.02
    ratchet_max_drawdown_tol: float = 0.10
    ratchet_min_n_trades: int = 5
    ratchet_max_symbol_regression: float = 0.5

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
