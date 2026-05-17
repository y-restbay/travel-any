import json
import logging
import time
import asyncio
from typing import AsyncIterator, Optional, Set

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatResumeRequest, ChatStreamRequest
from app.services.chat_service import (
    chat_stream,
    chat_stream_with_supervisor,
    chat_stream_with_tools,
    resume_supervisor_stream,
)
from app.services.config_service import get_active_llm_config, get_active_system_prompt
from app.services.llm_factory import uses_mock_provider
from app.services.tool_service import get_active_tools
from app.services.web_search_context import WEB_SEARCH_OFF_BLOCK

router = APIRouter(prefix="/chat", tags=["chat"])

logger = logging.getLogger("app.chat")


def _last_user_text(messages) -> str:
    for m in reversed(messages):
        if m.role == "user" and m.content.strip():
            text = m.content.strip().replace("\n", " ")
            return text[:200] + ("…" if len(text) > 200 else "")
    return "(空)"


async def _logged_stream(gen: AsyncIterator[str], question: str) -> AsyncIterator[str]:
    """包装 SSE 生成器:记录提问 / 回答完成 / 回答异常,工具报错由全局 handler 自动捕获。"""
    t0 = time.time()
    yield "event: status\ndata: {\"detail\":\"已收到问题，正在连接模型...\"}\n\n"
    await asyncio.sleep(0)
    try:
        async for event in gen:
            yield event
        logger.info("回答完成 | 用时 %.1fs | 问:%s", time.time() - t0, question)
    except Exception:
        logger.exception("回答异常 | 用时 %.1fs | 问:%s", time.time() - t0, question)
        raise


def _resolve_tavily_key(tools) -> Optional[str]:
    """从活跃工具里取 Tavily key;留空则返回 None,由客户端回退环境变量。"""
    for t in tools:
        if t.tool_type == "tavily_realtime_search":
            try:
                cfg = json.loads(t.config) if isinstance(t.config, str) else (t.config or {})
            except (json.JSONDecodeError, TypeError):
                cfg = {}
            return (cfg.get("api_key") or "").strip() or None
    return None


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# 联网搜索工具统一受「联网搜索」开关管控:关闭时不下发给模型。
_WEB_SEARCH_TOOL_TYPES = {"tavily_realtime_search", "firecrawl_search", "firecrawl_scrape"}


_WEATHER_INTENT_WORDS = (
    "天气", "气温", "温度", "下雨", "降雨", "降雪", "预报", "穿衣", "紫外线", "台风", "风力",
)
_DIRECTIONS_INTENT_WORDS = (
    "地图", "路线", "动线", "导航", "怎么走", "交通", "驾车", "自驾", "步行", "打车",
    "通勤", "路程", "距离", "显示出来",
)
_ITINERARY_CARD_INTENT_WORDS = (
    "生成卡片", "行程卡片", "显示卡片", "可视化行程", "结构化行程", "系统卡片", "卡片展示",
)
_EXPORT_INTENT_WORDS = (
    "导出", "下载", "保存成", "生成pdf", "生成 pdf", "pdf", "word", "文档",
)
_SEARCH_INTENT_WORDS = (
    "联网", "搜索", "查最新", "实时", "最新", "官网", "新闻", "营业时间", "票价", "门票",
)


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _single_mode_requested_tool_types(question: str, *, web_search: bool) -> Set[str]:
    """普通模式只响应用户显式要求的工具能力。

    ReAct 深度思考模式可以由模型自主选择工具；普通模式为了避免泄漏工具过程、
    避免“单 Agent 自己规划工具”，必须先由入口层根据用户最后一句收窄工具集合。
    """
    text = (question or "").lower()
    requested: Set[str] = set()

    if web_search:
        requested.update({"tavily_realtime_search", "firecrawl_search", "firecrawl_scrape"})
    if _has_any(text, _WEATHER_INTENT_WORDS):
        requested.add("qweather_weather")
    if _has_any(text, _DIRECTIONS_INTENT_WORDS):
        requested.add("amap_directions")
    if _has_any(text, _ITINERARY_CARD_INTENT_WORDS):
        requested.add("itinerary_summary")
    if _has_any(text, _EXPORT_INTENT_WORDS):
        requested.update({"itinerary_export", "itinerary_summary"})

    return requested


def _filter_tools_by_type(tools, allowed_types: Set[str]):
    if not allowed_types:
        return []
    return [tool for tool in tools if tool.tool_type in allowed_types]


@router.post("/stream")
async def stream_chat(payload: ChatStreamRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    llm_config = get_active_llm_config(db)
    system_prompt = get_active_system_prompt(db)

    active_tools = get_active_tools(db)
    mode = (payload.mode or "single").strip().lower()
    question = _last_user_text(payload.messages)

    knowledge_source = (payload.knowledge_source or "local").strip().lower()
    is_mock = uses_mock_provider(llm_config)
    # 联网搜索与云知识库互斥;mock 不消费上下文故不启用。
    web_search = bool(payload.web_search) and knowledge_source != "cloud" and not is_mock
    web_search_api_key = _resolve_tavily_key(active_tools) if web_search else None
    # 开关关闭时，联网类工具不进入模型可调用集合（路由判定仍用全量 active_tools）。
    effective_tools = (
        active_tools
        if web_search
        else [t for t in active_tools if t.tool_type not in _WEB_SEARCH_TOOL_TYPES]
    )
    user_wants_web_search = _has_any(question.lower(), _SEARCH_INTENT_WORDS)
    single_mode_tool_types = _single_mode_requested_tool_types(question, web_search=web_search)
    single_mode_tools = _filter_tools_by_type(effective_tools, single_mode_tool_types)

    if knowledge_source == "cloud":
        from app.services.bailian_app_service import bailian_app_chat_stream

        stream = bailian_app_chat_stream(payload.messages)
    elif mode == "deep_thinking" and active_tools and not is_mock:
        from app.services.react_chat_service import chat_stream_with_react

        stream = chat_stream_with_react(
            payload.messages, llm_config, system_prompt, effective_tools, knowledge_source,
            web_search, web_search_api_key,
        )
    elif single_mode_tools and not is_mock:
        # 普通模式只在用户明确要求某类工具能力时进入工具链，并且只下发对应工具。
        # 模型自主决定“下一步该调什么工具”的能力保留给 ReAct 深度思考模式。
        stream = chat_stream_with_tools(
            payload.messages, llm_config, system_prompt, single_mode_tools, knowledge_source,
            web_search, web_search_api_key,
        )
    else:
        # 没有可用工具时才走纯对话真 token 流式 SSE。
        stream = chat_stream(
            payload.messages,
            llm_config,
            system_prompt,
            knowledge_source,
            WEB_SEARCH_OFF_BLOCK if user_wants_web_search and not web_search else "",
        )

    logger.info(
        "提问 | mode=%s ks=%s web=%s tools=%s | %s",
        mode, knowledge_source, web_search, ",".join(sorted(single_mode_tool_types)) or "-",
        question,
    )
    return StreamingResponse(
        _logged_stream(stream, question),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/resume")
async def resume_chat(payload: ChatResumeRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """对前一个 SSE 流里 interrupt 事件的回复。仅 supervisor 模式有效。"""
    llm_config = get_active_llm_config(db)
    system_prompt = get_active_system_prompt(db)
    stream = resume_supervisor_stream(
        payload.decision,
        thread_id=payload.conversation_id,
        llm_config=llm_config,
        system_prompt=system_prompt,
    )
    return StreamingResponse(stream, media_type="text/event-stream", headers=_SSE_HEADERS)
