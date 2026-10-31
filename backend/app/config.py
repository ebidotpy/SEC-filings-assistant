import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Backend environment — single source of truth for configuration."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql://postgres:postgres@localhost:5434/document_copilot"

    jwt_secret_key: str = (
        "document-copilot-dev-secret-key-change-in-production-1234567890"
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 10080

    openai_api_key: str
    base_url: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    openai_embedding_max_chunk_tokens: int = 512
    openai_chat_model: str = "gpt-5-mini"

    agent_temperature: float = 0.2
    agent_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "low"
    agent_max_requests: int = 20
    agent_max_tool_calls: int = 30
    agent_output_retries: int = 2

    log_level: str = "INFO"
    log_json: bool = False

    logfire_token: str | None = None
    logfire_send_to_logfire: str = "if-token-present"
    logfire_service_name: str = "document-copilot-agent"
    logfire_environment: str = "development"
    logfire_instrument_pydantic_ai: bool = True
    logfire_instrument_system_metrics: bool = True

    retrieval_candidate_k: int = 50
    retrieval_top_k: int = 10
    retrieval_rrf_k: int = 60
    retrieval_neighbor_radius: int = 1
    retrieval_semantic_min_similarity: float = 0.0
    retrieval_keyword_model: str = "gpt-5-nano"
    retrieval_keyword_temperature: float = 0.0

    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def mirror_openai_env(self) -> "Settings":
        # OpenAI SDK reads OPENAI_API_KEY and OPENAI_BASE_URL from the environment when not passed explicitly.
        os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.base_url is not None:
            os.environ["OPENAI_BASE_URL"] = self.base_url
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
