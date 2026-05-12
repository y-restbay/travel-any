from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WanderBot API"
    api_prefix: str = "/api"
    database_url: str = Field(
        default=f"sqlite:///{Path(__file__).resolve().parents[3] / 'wanderbot.db'}"
    )
    rag_chroma_path: str = Field(
        default=str(Path(__file__).resolve().parents[3] / "storage" / "chroma")
    )
    rag_bm25_path: str = Field(
        default=str(Path(__file__).resolve().parents[3] / "storage" / "bm25_index.json")
    )
    rag_embedding_provider: str = Field(default="hash")
    rag_embedding_model: str = Field(default="")
    rag_embedding_api_key: Optional[str] = Field(default=None)
    rag_embedding_base_url: Optional[str] = Field(default=None)
    rag_embedding_timeout: float = Field(default=20.0)
    cors_origins: List[str] = [
        "http://localhost:6789",
        "http://127.0.0.1:6789",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # 允许 .env 里出现工具相关的环境变量（如 QWEATHER_KEY）而不报错
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
