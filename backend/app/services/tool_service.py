import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import Tool
from app.schemas.config import is_masked_secret
from app.travel_tools.realtime_search_tool import REALTIME_SEARCH_DESCRIPTION


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
        try:
            existing_config = json.loads(tool.config or "{}")
        except json.JSONDecodeError:
            existing_config = {}
        next_config = dict(config)
        for key, value in list(next_config.items()):
            if is_masked_secret(value):
                next_config[key] = existing_config.get(key, "")
        tool.config = json.dumps(next_config, ensure_ascii=False)
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
    {
        "name": "get_weather",
        "label": "Weather (QWeather)",
        "description": (
            "查询任意城市的实时天气或未来 3/7 天天气预报，可选生活指数与逐小时数据。"
            "用户询问某地天气、是否下雨、穿衣建议、出行天气、紫外线、台风预警等情况时使用。"
        ),
        "tool_type": "qweather_weather",
        # 留空表示从环境变量 QWEATHER_KEY 读取；填写则覆盖之
        "config": {"api_key": "", "weather_host": "", "geo_host": ""},
    },
    {
        "name": "search_realtime_travel_info",
        "label": "Realtime Travel Search (Tavily)",
        "description": REALTIME_SEARCH_DESCRIPTION,
        "tool_type": "tavily_realtime_search",
        # 留空表示从环境变量 TAVILY_API_KEY 读取；填写则覆盖之
        "config": {"api_key": ""},
    },
    {
        "name": "get_directions",
        "label": "Directions (Amap)",
        "description": (
            "规划多个地点之间的驾车 / 步行路线，并把路线推送到用户右侧的地图区域。"
            "用户问 'A 到 B 怎么走'、推荐多个景点后串成行程、多日动线规划时使用。"
            "未配置 AMAP_KEY 时使用 mock 数据，仍可在地图上看到示意路径。"
        ),
        "tool_type": "amap_directions",
        # 留空表示从环境变量 AMAP_KEY 读取；填写则覆盖之
        "config": {"api_key": "", "host": ""},
    },
    {
        "name": "generate_itinerary_summary",
        "label": "Itinerary Summary",
        "description": (
            "把多轮工具调用收集到的天气、景点、路线整合成结构化行程，"
            "推送给前端渲染 '行程卡片'，并在缓存中保留供导出使用。"
            "完成天气 + 各日动线规划后主动调用一次。"
        ),
        "tool_type": "itinerary_summary",
        "config": {},
    },
    {
        "name": "export_itinerary",
        "label": "Itinerary Export",
        "description": (
            "把已生成的行程导出为 PDF 或 Word 文件，并通过 SSE 推送下载链接。"
            "用户表示要下载、保存、导出时调用；默认 PDF。"
        ),
        "tool_type": "itinerary_export",
        "config": {},
    },
    {
        "name": "identify_landmark",
        "label": "Identify Landmark (VLM)",
        "description": (
            "识别用户上传图片中的景点或地标，内部调用国内多模态大模型（默认 qwen-vl-max）。"
            "当用户消息携带 image_ref 时主动调用，拿到景点名称后可继续调用 "
            "search_realtime_travel_info / get_weather / get_directions 编排完整回答。"
            "VLM 配置在管理后台「图片识别模型」单独管理；留空时回退到环境变量 DASHSCOPE_API_KEY。"
        ),
        "tool_type": "landmark_identify",
        "config": {"model": "", "base_url": "", "api_key": ""},
    },
]
