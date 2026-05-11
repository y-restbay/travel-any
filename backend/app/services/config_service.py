from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import LLMConfig, SystemPrompt
from app.schemas.config import AdminConfigUpdate, LLMConfigCreate, LLMConfigUpdate, SystemPromptCreate


DEFAULT_PROMPT = (
    "你是 WanderBot，一个专业、克制、审美优秀的全球旅游规划师。"
    "你会根据用户的偏好、预算、季节、同行人群和节奏，给出清晰、温暖、可执行的旅行建议。"
    "回答时优先给出可落地的行程、住宿区域、交通和避坑提示。"
)


def _deactivate_others(db: Session, model: type, active_id: int) -> None:
    db.query(model).filter(model.id != active_id).update({"is_active": False})


def ensure_defaults(db: Session) -> None:
    if db.scalar(select(LLMConfig).limit(1)) is None:
        db.add(
            LLMConfig(
                provider="Mock",
                model_name="wanderbot-mock",
                api_key="",
                base_url="",
                is_active=True,
            )
        )

    if db.scalar(select(SystemPrompt).limit(1)) is None:
        db.add(
            SystemPrompt(
                name="WanderBot Default",
                content=DEFAULT_PROMPT,
                is_active=True,
            )
        )

    db.commit()


def get_active_llm_config(db: Session) -> LLMConfig:
    config = db.scalar(select(LLMConfig).where(LLMConfig.is_active.is_(True)).order_by(LLMConfig.id))
    if config is None:
        ensure_defaults(db)
        config = db.scalar(select(LLMConfig).order_by(LLMConfig.id))
    return config


def get_active_system_prompt(db: Session) -> SystemPrompt:
    prompt = db.scalar(select(SystemPrompt).where(SystemPrompt.is_active.is_(True)).order_by(SystemPrompt.id))
    if prompt is None:
        ensure_defaults(db)
        prompt = db.scalar(select(SystemPrompt).order_by(SystemPrompt.id))
    return prompt


def list_llm_configs(db: Session) -> list[LLMConfig]:
    ensure_defaults(db)
    return list(db.scalars(select(LLMConfig).order_by(LLMConfig.id)).all())


def create_llm_config(db: Session, payload: LLMConfigCreate) -> LLMConfig:
    config = LLMConfig(**payload.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, LLMConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def update_llm_config(db: Session, config_id: int, payload: LLMConfigUpdate) -> Optional[LLMConfig]:
    config = db.get(LLMConfig, config_id)
    if config is None:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, LLMConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def delete_llm_config(db: Session, config_id: int) -> bool:
    config = db.get(LLMConfig, config_id)
    if config is None:
        return False
    db.delete(config)
    db.commit()
    ensure_defaults(db)
    return True


def list_system_prompts(db: Session) -> list[SystemPrompt]:
    ensure_defaults(db)
    return list(db.scalars(select(SystemPrompt).order_by(SystemPrompt.id)).all())


def create_system_prompt(db: Session, payload: SystemPromptCreate) -> SystemPrompt:
    prompt = SystemPrompt(**payload.model_dump())
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    if prompt.is_active:
        _deactivate_others(db, SystemPrompt, prompt.id)
        db.commit()
        db.refresh(prompt)
    return prompt


def update_system_prompt(db: Session, prompt_id: int, payload) -> Optional[SystemPrompt]:
    prompt = db.get(SystemPrompt, prompt_id)
    if prompt is None:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(prompt, key, value)

    db.commit()
    db.refresh(prompt)
    if prompt.is_active:
        _deactivate_others(db, SystemPrompt, prompt.id)
        db.commit()
        db.refresh(prompt)
    return prompt


def update_active_admin_config(db: Session, payload: AdminConfigUpdate) -> tuple[LLMConfig, SystemPrompt]:
    llm_config = get_active_llm_config(db)
    system_prompt = get_active_system_prompt(db)

    for key, value in payload.llm_config.model_dump(exclude_unset=True).items():
        setattr(llm_config, key, value)
    llm_config.is_active = True

    for key, value in payload.system_prompt.model_dump(exclude_unset=True).items():
        setattr(system_prompt, key, value)
    system_prompt.is_active = True

    db.commit()
    db.refresh(llm_config)
    db.refresh(system_prompt)
    return llm_config, system_prompt
