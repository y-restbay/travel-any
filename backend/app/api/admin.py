from datetime import datetime

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.admin_auth import create_admin_token, require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.config import (
    AdminConfigRead,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminConfigUpdate,
    EmbeddingConfigCreate,
    EmbeddingConfigRead,
    EmbeddingConfigUpdate,
    LLMConfigCreate,
    LLMConfigRead,
    LLMConfigUpdate,
    SystemLogEntry,
    SystemPromptCreate,
    SystemPromptRead,
    SystemPromptUpdate,
    TestEmbeddingRequest,
    TestEmbeddingResponse,
    TestLLMRequest,
    TestLLMResponse,
    ToolCreate,
    ToolRead,
    ToolUpdate,
)
from app.services import config_service, tool_service
from app.services.chat_service import test_llm_connection
from app.services.log_buffer import clear_logs, get_logs

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest) -> AdminLoginResponse:
    settings = get_settings()
    if not (
        secrets.compare_digest(payload.username, settings.admin_username)
        and secrets.compare_digest(payload.password, settings.admin_password)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")
    return AdminLoginResponse(token=create_admin_token(settings.admin_username), username=settings.admin_username)


# ---- LLM Config & System Prompt ----

@router.get("/config", response_model=AdminConfigRead)
def read_active_config(db: Session = Depends(get_db)) -> AdminConfigRead:
    config_service.ensure_defaults(db)
    return AdminConfigRead(
        llm_config=config_service.get_active_llm_config(db),
        system_prompt=config_service.get_active_system_prompt(db),
    )


@router.put("/config", response_model=AdminConfigRead)
def update_active_config(
    payload: AdminConfigUpdate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminConfigRead:
    llm_config, system_prompt = config_service.update_active_admin_config(db, payload)
    return AdminConfigRead(llm_config=llm_config, system_prompt=system_prompt)


@router.post("/config/test", response_model=TestLLMResponse)
async def test_config(payload: TestLLMRequest, _: str = Depends(require_admin)) -> TestLLMResponse:
    result = await test_llm_connection(
        provider=payload.provider,
        model_name=payload.model_name,
        api_key=payload.api_key,
        base_url=payload.base_url,
    )
    return TestLLMResponse(**result)


@router.post("/config/embeddings/test", response_model=TestEmbeddingResponse)
async def test_embedding_config(
    payload: TestEmbeddingRequest,
    _: str = Depends(require_admin),
) -> TestEmbeddingResponse:
    import time
    from types import SimpleNamespace

    from app.core.config import get_settings
    from app.rag.embeddings import create_embedding_function

    start = time.time()
    try:
        embedding = create_embedding_function(
            get_settings(),
            SimpleNamespace(
                provider=payload.provider,
                model_name=payload.model_name,
                api_key=payload.api_key,
                base_url=payload.base_url,
            ),
        )
        vector = embedding.embed_query("WanderBot embedding connection test")
        latency = int((time.time() - start) * 1000)
        return TestEmbeddingResponse(
            success=True,
            latency_ms=latency,
            message=f"连接成功（{latency}ms），向量维度：{len(vector)}",
        )
    except Exception as exc:
        latency = int((time.time() - start) * 1000)
        return TestEmbeddingResponse(
            success=False,
            latency_ms=latency,
            message=f"连接失败（{latency}ms）：{exc}",
        )


@router.get("/config/llm", response_model=list[LLMConfigRead])
def list_llm_configs(_: str = Depends(require_admin), db: Session = Depends(get_db)) -> list[LLMConfigRead]:
    return config_service.list_llm_configs(db)


@router.post("/config/llm", response_model=LLMConfigRead, status_code=status.HTTP_201_CREATED)
def create_llm_config(
    payload: LLMConfigCreate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LLMConfigRead:
    return config_service.create_llm_config(db, payload)


@router.patch("/config/llm/{config_id}", response_model=LLMConfigRead)
def update_llm_config(
    config_id: int,
    payload: LLMConfigUpdate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LLMConfigRead:
    config = config_service.update_llm_config(db, config_id, payload)
    if config is None:
        raise HTTPException(status_code=404, detail="LLM config not found")
    return config


@router.delete("/config/llm/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_config(config_id: int, _: str = Depends(require_admin), db: Session = Depends(get_db)) -> None:
    if not config_service.delete_llm_config(db, config_id):
        raise HTTPException(status_code=404, detail="LLM config not found")


@router.get("/config/embeddings", response_model=list[EmbeddingConfigRead])
def list_embedding_configs(
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[EmbeddingConfigRead]:
    return config_service.list_embedding_configs(db)


@router.post("/config/embeddings", response_model=EmbeddingConfigRead, status_code=status.HTTP_201_CREATED)
def create_embedding_config(
    payload: EmbeddingConfigCreate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmbeddingConfigRead:
    from app.rag.pipeline import get_rag_pipeline

    config = config_service.create_embedding_config(db, payload)
    get_rag_pipeline.cache_clear()
    return config


@router.patch("/config/embeddings/{config_id}", response_model=EmbeddingConfigRead)
def update_embedding_config(
    config_id: int,
    payload: EmbeddingConfigUpdate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmbeddingConfigRead:
    from app.rag.pipeline import get_rag_pipeline

    config = config_service.update_embedding_config(db, config_id, payload)
    if config is None:
        raise HTTPException(status_code=404, detail="Embedding config not found")
    get_rag_pipeline.cache_clear()
    return config


@router.delete("/config/embeddings/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_embedding_config(
    config_id: int,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    from app.rag.pipeline import get_rag_pipeline

    if not config_service.delete_embedding_config(db, config_id):
        raise HTTPException(status_code=404, detail="Embedding config not found")
    get_rag_pipeline.cache_clear()


@router.get("/config/prompts", response_model=list[SystemPromptRead])
def list_system_prompts(_: str = Depends(require_admin), db: Session = Depends(get_db)) -> list[SystemPromptRead]:
    return config_service.list_system_prompts(db)


@router.post("/config/prompts", response_model=SystemPromptRead, status_code=status.HTTP_201_CREATED)
def create_system_prompt(
    payload: SystemPromptCreate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemPromptRead:
    return config_service.create_system_prompt(db, payload)


@router.patch("/config/prompts/{prompt_id}", response_model=SystemPromptRead)
def update_system_prompt(
    prompt_id: int,
    payload: SystemPromptUpdate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemPromptRead:
    prompt = config_service.update_system_prompt(db, prompt_id, payload)
    if prompt is None:
        raise HTTPException(status_code=404, detail="System prompt not found")
    return prompt


@router.delete("/config/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system_prompt(
    prompt_id: int,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    if not config_service.delete_system_prompt(db, prompt_id):
        raise HTTPException(status_code=404, detail="System prompt not found")


# ---- Tools ----

@router.get("/tools", response_model=list[ToolRead])
def list_tools(_: str = Depends(require_admin), db: Session = Depends(get_db)) -> list[ToolRead]:
    return tool_service.list_tools(db)


@router.get("/tools/presets")
def list_tool_presets(_: str = Depends(require_admin)):
    return tool_service.TOOL_PRESETS


@router.post("/tools", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
def create_tool(
    payload: ToolCreate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ToolRead:
    return tool_service.create_tool(
        db,
        name=payload.name,
        label=payload.label,
        description=payload.description,
        tool_type=payload.tool_type,
        config=payload.config,
        is_active=payload.is_active,
    )


@router.get("/tools/{tool_id}", response_model=ToolRead)
def get_tool(tool_id: int, _: str = Depends(require_admin), db: Session = Depends(get_db)) -> ToolRead:
    tool = tool_service.get_tool(db, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.patch("/tools/{tool_id}", response_model=ToolRead)
def update_tool(
    tool_id: int,
    payload: ToolUpdate,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ToolRead:
    tool = tool_service.update_tool(
        db,
        tool_id=tool_id,
        name=payload.name,
        label=payload.label,
        description=payload.description,
        tool_type=payload.tool_type,
        config=payload.config,
        is_active=payload.is_active,
    )
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(tool_id: int, _: str = Depends(require_admin), db: Session = Depends(get_db)) -> None:
    if not tool_service.delete_tool(db, tool_id):
        raise HTTPException(status_code=404, detail="Tool not found")


# ---- System Logs ----

@router.get("/logs", response_model=list[SystemLogEntry])
def read_system_logs(
    level: str = "ALL",
    q: str = "",
    limit: int = 200,
    _: str = Depends(require_admin),
) -> list[SystemLogEntry]:
    """运行日志查看:level 为等级阈值(ALL/INFO/WARNING/ERROR),q 关键词,limit 上限。"""
    bounded = min(max(limit, 1), 1000)
    return get_logs(level=level, query=q or None, limit=bounded)


@router.delete("/logs", status_code=status.HTTP_204_NO_CONTENT)
def clear_system_logs(_: str = Depends(require_admin)) -> None:
    clear_logs()


@router.get("/logs/export")
def export_system_logs(
    level: str = "ALL",
    q: str = "",
    _: str = Depends(require_admin),
) -> PlainTextResponse:
    """按当前筛选条件把日志导出为可下载的 .log 文本(按时间正序)。"""
    rows = get_logs(level=level, query=q or None, limit=1000)
    lines = [
        f"[{datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M:%S')}] "
        f"{r['level']:<8} {r['logger']} | {r['message']}"
        for r in reversed(rows)  # get_logs 最新在前,导出反转回时间正序
    ]
    content = ("\n".join(lines) + "\n") if lines else "(无符合条件的日志)\n"
    filename = f"wanderbot-logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
