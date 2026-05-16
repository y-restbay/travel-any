from datetime import datetime
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class TestLLMRequest(BaseModel):
    provider: str = "Mock"
    model_name: str = "wanderbot-mock"
    api_key: str = ""
    base_url: str = ""


class TestLLMResponse(BaseModel):
    success: bool
    latency_ms: int = 0
    message: str = ""


class TestEmbeddingRequest(BaseModel):
    provider: str = "hash"
    model_name: str = "hash-384"
    api_key: str = ""
    base_url: str = ""


class TestEmbeddingResponse(BaseModel):
    success: bool
    latency_ms: int = 0
    message: str = ""


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    username: str


def mask_secret(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if value.startswith("***"):
        return value
    if len(value) <= 8:
        return "***"
    return f"***{value[-4:]}"


def is_masked_secret(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("***")


def mask_secret_config(config: Any) -> Any:
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            return {}
    if not isinstance(config, dict):
        return config
    masked: dict[str, Any] = {}
    for key, value in config.items():
        lowered = str(key).lower()
        if any(token in lowered for token in ("api_key", "secret", "token", "password")):
            masked[key] = mask_secret(value)
        else:
            masked[key] = value
    return masked


class ToolBase(BaseModel):
    name: str
    label: str = ""
    description: str = ""
    tool_type: str = "firecrawl_search"
    config: Dict[str, Any] = {}
    is_active: bool = True


class ToolCreate(ToolBase):
    pass


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    tool_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ToolRead(ToolBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("config", mode="before")
    @classmethod
    def parse_config(cls, v: Any) -> Any:
        return mask_secret_config(v)


class LLMConfigBase(BaseModel):
    provider: str = "Mock"
    model_name: str = "wanderbot-mock"
    api_key: str = ""
    base_url: str = ""
    runtime: str = "tools"  # 'tools' | 'supervisor'
    is_active: bool = True


class LLMConfigCreate(LLMConfigBase):
    pass


class LLMConfigUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    runtime: Optional[str] = None
    is_active: Optional[bool] = None


class LLMConfigRead(LLMConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("api_key", mode="before")
    @classmethod
    def mask_api_key(cls, v: Any) -> Any:
        return mask_secret(v)


class EmbeddingConfigBase(BaseModel):
    provider: str = "hash"
    model_name: str = "hash-384"
    api_key: str = ""
    base_url: str = ""
    is_active: bool = True


class EmbeddingConfigCreate(EmbeddingConfigBase):
    pass


class EmbeddingConfigUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None


class EmbeddingConfigRead(EmbeddingConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("api_key", mode="before")
    @classmethod
    def mask_api_key(cls, v: Any) -> Any:
        return mask_secret(v)


class SystemPromptBase(BaseModel):
    name: str = "Default Travel Planner"
    content: str
    knowledge_scope: list[str] = []
    is_active: bool = True


class SystemPromptCreate(SystemPromptBase):
    pass


class SystemPromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    knowledge_scope: Optional[list[str]] = None
    is_active: Optional[bool] = None


class SystemPromptRead(SystemPromptBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("knowledge_scope", mode="before")
    @classmethod
    def parse_knowledge_scope(cls, v: Any) -> Any:
        if v in (None, ""):
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return v


class AdminConfigRead(BaseModel):
    llm_config: LLMConfigRead
    system_prompt: SystemPromptRead


class AdminConfigUpdate(BaseModel):
    llm_config: LLMConfigUpdate
    system_prompt: SystemPromptUpdate


class SystemLogEntry(BaseModel):
    id: int
    ts: float
    level: str
    logger: str
    message: str
