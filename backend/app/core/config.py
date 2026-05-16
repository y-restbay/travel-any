from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WanderBot API"
    api_prefix: str = "/api"
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="admin123")
    admin_token_secret: Optional[str] = Field(default=None)
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
    # 阿里云百炼云知识库 Retrieve 纯检索接口（云端已重排）。
    bailian_access_key_id: Optional[str] = Field(default=None)
    bailian_access_key_secret: Optional[str] = Field(default=None)
    bailian_workspace_id: Optional[str] = Field(default=None)
    bailian_index_id: Optional[str] = Field(default=None)
    bailian_endpoint: str = Field(default="bailian.cn-beijing.aliyuncs.com")
    bailian_timeout: float = Field(default=15.0)
    # 百炼应用降级通道：使用 DashScope sk 调用已绑定知识库的百炼应用，由百炼直接生成回答。
    bailian_app_api_key: Optional[str] = Field(default=None)
    bailian_app_id: Optional[str] = Field(default=None)
    bailian_app_workspace_id: Optional[str] = Field(default=None)
    bailian_app_base_url: str = Field(default="https://dashscope.aliyuncs.com/api/v1")
    bailian_app_timeout: float = Field(default=60.0)
    # Official/common DashScope aliases. The Bailian app channel accepts either naming style.
    dashscope_api_key: Optional[str] = Field(default=None)
    dashscope_workspace_id: Optional[str] = Field(default=None)
    app_id: Optional[str] = Field(default=None)
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
