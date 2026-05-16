import json
import logging
import time
import uuid
from typing import AsyncIterator, Optional

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

# 仅自定义的 Tavily 实时搜索工具受联网搜索开关管控:关闭时不下发给模型。
# firecrawl 的 web_search / web_scrape、天气/路线等领域 API 与本地工具均不受影响，始终可用。
_WEB_SEARCH_TOOL_TYPES = {"tavily_realtime_search"}


@router.post("/stream")
async def stream_chat(payload: ChatStreamRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    llm_config = get_active_llm_config(db)
    system_prompt = get_active_system_prompt(db)

    active_tools = get_active_tools(db)
    mode = (payload.mode or "single").strip().lower()
    runtime = (llm_config.runtime or "tools").lower().strip()

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

    if knowledge_source == "cloud":
        from app.services.bailian_app_service import bailian_app_chat_stream

        stream = bailian_app_chat_stream(payload.messages)
    elif mode == "deep_thinking" and active_tools and not is_mock:
        from app.services.react_chat_service import chat_stream_with_react

        stream = chat_stream_with_react(
            payload.messages, llm_config, system_prompt, effective_tools, knowledge_source,
            web_search, web_search_api_key,
        )
    elif runtime == "supervisor" and not is_mock and not web_search:
        # 联网搜索时绕过 supervisor，走已支持注入的 tools 路径。
        thread_id = payload.conversation_id or uuid.uuid4().hex
        stream = chat_stream_with_supervisor(
            payload.messages, llm_config, system_prompt, thread_id=thread_id, knowledge_source=knowledge_source
        )
    elif (active_tools or web_search) and not is_mock:
        stream = chat_stream_with_tools(
            payload.messages, llm_config, system_prompt, effective_tools, knowledge_source,
            web_search, web_search_api_key,
        )
    else:
        stream = chat_stream(payload.messages, llm_config, system_prompt, knowledge_source)

    question = _last_user_text(payload.messages)
    logger.info(
        "提问 | mode=%s ks=%s web=%s | %s",
        mode, knowledge_source, web_search, question,
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
