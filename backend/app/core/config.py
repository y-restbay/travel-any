from functools import lru_cache
from pathlib import Path
from typing import List

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
    cors_origins: List[str] = [
        "http://localhost:6789",
        "http://127.0.0.1:6789",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
