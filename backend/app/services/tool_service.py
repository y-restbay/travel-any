import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import Tool


def list_tools(db: Session) -> list[Tool]:
    return list(db.scalars(select(Tool).order_by(Tool.id)).all())


def get_active_tools(db: Session) -> list[Tool]:
    return list(
        db.scalars(
            select(Tool).where(Tool.is_active.is_(True)).order_by(Tool.id)
        ).all()
    )


def get_tool(db: Session, tool_id: int) -> Optional[Tool]:
    return db.get(Tool, tool_id)


def create_tool(
    db: Session,
    name: str,
    label: str = "",
    description: str = "",
    tool_type: str = "firecrawl_search",
    config: Optional[Dict[str, Any]] = None,
    is_active: bool = True,
) -> Tool:
    tool = Tool(
        name=name,
        label=label or name,
        description=description,
        tool_type=tool_type,
        config=json.dumps(config or {}, ensure_ascii=False),
        is_active=is_active,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


def update_tool(
    db: Session,
    tool_id: int,
    name: Optional[str] = None,
    label: Optional[str] = None,
    description: Optional[str] = None,
    tool_type: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    is_active: Optional[bool] = None,
) -> Optional[Tool]:
    tool = db.get(Tool, tool_id)
    if tool is None:
        return None

    if name is not None:
        tool.name = name
    if label is not None:
        tool.label = label
    if description is not None:
        tool.description = description
    if tool_type is not None:
        tool.tool_type = tool_type
    if config is not None:
        tool.config = json.dumps(config, ensure_ascii=False)
    if is_active is not None:
        tool.is_active = is_active

    db.commit()
    db.refresh(tool)
    return tool


def delete_tool(db: Session, tool_id: int) -> bool:
    tool = db.get(Tool, tool_id)
    if tool is None:
        return False
    db.delete(tool)
    db.commit()
    return True


TOOL_PRESETS: List[Dict[str, Any]] = [
    {
        "name": "web_search",
        "label": "Web Search",
        "description": "搜索互联网获取最新的旅行信息、价格、营业时间、评价和新闻。当需要实时信息时使用。",
        "tool_type": "firecrawl_search",
        "config": {"api_key": ""},
    },
    {
        "name": "web_scrape",
        "label": "Web Scrape",
        "description": "从指定 URL 提取内容。当需要某个具体网页的详细信息时使用。",
        "tool_type": "firecrawl_scrape",
        "config": {"api_key": ""},
    },
]
