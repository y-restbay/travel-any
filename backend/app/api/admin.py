from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.config import (
    AdminConfigRead,
    AdminConfigUpdate,
    LLMConfigCreate,
    LLMConfigRead,
    LLMConfigUpdate,
    SystemPromptCreate,
    SystemPromptRead,
    SystemPromptUpdate,
    TestLLMRequest,
    TestLLMResponse,
    ToolCreate,
    ToolRead,
    ToolUpdate,
)
from app.services import config_service, tool_service
from app.services.chat_service import test_llm_connection

router = APIRouter(prefix="/admin", tags=["admin"])


# ---- LLM Config & System Prompt ----

@router.get("/config", response_model=AdminConfigRead)
def read_active_config(db: Session = Depends(get_db)) -> AdminConfigRead:
    config_service.ensure_defaults(db)
    return AdminConfigRead(
        llm_config=config_service.get_active_llm_config(db),
        system_prompt=config_service.get_active_system_prompt(db),
    )


@router.put("/config", response_model=AdminConfigRead)
def update_active_config(payload: AdminConfigUpdate, db: Session = Depends(get_db)) -> AdminConfigRead:
    llm_config, system_prompt = config_service.update_active_admin_config(db, payload)
    return AdminConfigRead(llm_config=llm_config, system_prompt=system_prompt)


@router.post("/config/test", response_model=TestLLMResponse)
async def test_config(payload: TestLLMRequest) -> TestLLMResponse:
    result = await test_llm_connection(
        provider=payload.provider,
        model_name=payload.model_name,
        api_key=payload.api_key,
        base_url=payload.base_url,
    )
    return TestLLMResponse(**result)


@router.get("/config/llm", response_model=list[LLMConfigRead])
def list_llm_configs(db: Session = Depends(get_db)) -> list[LLMConfigRead]:
    return config_service.list_llm_configs(db)


@router.post("/config/llm", response_model=LLMConfigRead, status_code=status.HTTP_201_CREATED)
def create_llm_config(payload: LLMConfigCreate, db: Session = Depends(get_db)) -> LLMConfigRead:
    return config_service.create_llm_config(db, payload)


@router.patch("/config/llm/{config_id}", response_model=LLMConfigRead)
def update_llm_config(config_id: int, payload: LLMConfigUpdate, db: Session = Depends(get_db)) -> LLMConfigRead:
    config = config_service.update_llm_config(db, config_id, payload)
    if config is None:
        raise HTTPException(status_code=404, detail="LLM config not found")
    return config


@router.delete("/config/llm/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_config(config_id: int, db: Session = Depends(get_db)) -> None:
    if not config_service.delete_llm_config(db, config_id):
        raise HTTPException(status_code=404, detail="LLM config not found")


@router.get("/config/prompts", response_model=list[SystemPromptRead])
def list_system_prompts(db: Session = Depends(get_db)) -> list[SystemPromptRead]:
    return config_service.list_system_prompts(db)


@router.post("/config/prompts", response_model=SystemPromptRead, status_code=status.HTTP_201_CREATED)
def create_system_prompt(payload: SystemPromptCreate, db: Session = Depends(get_db)) -> SystemPromptRead:
    return config_service.create_system_prompt(db, payload)


@router.patch("/config/prompts/{prompt_id}", response_model=SystemPromptRead)
def update_system_prompt(
    prompt_id: int,
    payload: SystemPromptUpdate,
    db: Session = Depends(get_db),
) -> SystemPromptRead:
    prompt = config_service.update_system_prompt(db, prompt_id, payload)
    if prompt is None:
        raise HTTPException(status_code=404, detail="System prompt not found")
    return prompt


# ---- Tools ----

@router.get("/tools", response_model=list[ToolRead])
def list_tools(db: Session = Depends(get_db)) -> list[ToolRead]:
    return tool_service.list_tools(db)


@router.get("/tools/presets")
def list_tool_presets():
    return tool_service.TOOL_PRESETS


@router.post("/tools", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
def create_tool(payload: ToolCreate, db: Session = Depends(get_db)) -> ToolRead:
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
def get_tool(tool_id: int, db: Session = Depends(get_db)) -> ToolRead:
    tool = tool_service.get_tool(db, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.patch("/tools/{tool_id}", response_model=ToolRead)
def update_tool(tool_id: int, payload: ToolUpdate, db: Session = Depends(get_db)) -> ToolRead:
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
def delete_tool(tool_id: int, db: Session = Depends(get_db)) -> None:
    if not tool_service.delete_tool(db, tool_id):
        raise HTTPException(status_code=404, detail="Tool not found")
