"""深度思考模式（ReAct）的 SSE 流式实现。

与 ``chat_stream_with_tools`` 的差异:
- 工具调用前显式输出"思考"文本,通过 ``thought`` 事件流式推给前端
- 用一个特殊工具 ``signal_thinking_done`` 标记思考阶段结束
- 思考结束后用「不带 tools」的二次调用生成最终回答,通过 ``answer_chunk`` 推送
"""

import asyncio
import json
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool as langchain_tool

from app.models.config import LLMConfig, SystemPrompt
from app.schemas.chat import ChatMessage
from app.services.chat_service import (
    _augmented_system_prompt,
    _message_content_to_text,
    _rag_meta,
    _retrieve_for_messages,
    build_langchain_tools,
    sse_event,
    strip_tool_markup,
)
from app.services.llm_factory import create_chat_model
from app.services.metrics_service import (
    extract_usage_metadata,
    llm_duration_timer,
    observe_llm_tokens,
)
from app.services.react_prompts import ANSWER_STAGE_PROMPT, REACT_SYSTEM_PROMPT
from app.services.session_context_service import build_session_context
from app.services.web_search_context import build_web_search_context


MAX_THINKING_STEPS = 8


# DeepSeek 等模型在「content + tool_calls 混合」时会把工具调用的控制 token
# (含全角竖线 ｜U+FF5C 的特殊 token / invoke·parameter·tool_calls XML)
# 当普通文本吐出来。这里把它们从要展示的文本里抹掉,避免污染思考/回答面板。
_TOOL_MARKUP_RE = re.compile(
    r"<[^>]*｜[^>]*>"  # 含全角竖线的标签(DeepSeek 特殊 token)
    r"|</?\s*｜?｜?\s*DSML\s*｜?｜?[^>]*>"  # ｜｜DSML｜｜ 命名空间标签
    r"|</?\s*(?:invoke|parameter|tool_calls?|function_calls?)\b[^>]*>"  # 通用工具调用 XML
    r"|｜+\s*DSML\s*｜+",  # 残缺的 ｜｜DSML｜｜ 前缀(流式截断遗留)
    re.IGNORECASE,
)


def _strip_tool_markup(text: str) -> str:
    """抹掉泄漏到正文里的工具调用控制标记;顺带去掉流式截断的替换字符。"""
    if not text:
        return text
    return strip_tool_markup(_TOOL_MARKUP_RE.sub("", text).replace("�", ""))


def _iter_thought_pieces(text: str, size: int = 8) -> Iterator[str]:
    """把非流式拿到的思考文本切成小段,回放出"流式打字"的效果。"""
    for i in range(0, len(text), size):
        yield text[i : i + size]


@langchain_tool
def signal_thinking_done(summary: str = "") -> str:
    """当你已经通过工具调用收集到足够信息、准备给用户最终回答时,调用此工具标记思考阶段结束。

    重要:
    - 这是「深度思考模式」专用工具,调用后系统会自动切换到回答阶段
    - 即使是简单问题(例如只问天气),在拿到工具结果后也必须调用它来收尾
    - 不需要在 summary 里写完整回答,只写一句话总结接下来要回答什么即可

    参数:
    - summary: 一句话总结你将给用户什么样的回答(可选)
    """
    return json.dumps({"acknowledged": True, "summary": summary}, ensure_ascii=False)


def _summarize_observation(tool_name: str, raw_result: str) -> str:
    """从工具返回 JSON 文本提取一句话摘要给前端 observation 事件展示。"""
    try:
        data = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError):
        snippet = raw_result.strip()
        return snippet[:100] + ("…" if len(snippet) > 100 else "")

    if not isinstance(data, dict):
        return "已获取结果"

    if "error" in data:
        return f"⚠️ {data['error']}"

    if tool_name == "get_weather":
        location = data.get("地点") or data.get("location") or ""
        return f"已获取 {location} 天气" if location else "已获取天气信息"
    if tool_name == "get_directions":
        distance = data.get("总距离") or data.get("distance_text") or "?"
        return f"已规划路线，总距离 {distance}"
    if tool_name == "generate_itinerary_summary":
        days = data.get("天数") or data.get("day_count") or "?"
        return f"已整合行程（{days} 天）"
    if tool_name == "export_itinerary":
        fmt = data.get("文件格式") or data.get("format") or ""
        return f"已导出{fmt or '文档'}"
    if tool_name == "search_realtime_travel_info":
        count = data.get("结果数") or len(data.get("results", []) or [])
        return f"已联网搜索 {count} 条信息"
    if tool_name in {"web_search", "web_scrape"}:
        return "已完成网页检索"

    return "已获取结果"


def _build_lc_messages(
    messages: List[ChatMessage],
    system_prompt: SystemPrompt,
    retrieve_result,
    session_context,
    web_search_block: str = "",
) -> List[BaseMessage]:
    """在原有 system prompt 上叠加 ReAct 守则。"""
    base = _augmented_system_prompt(
        system_prompt, retrieve_result, session_context, web_search_block
    )
    augmented = f"{base}\n\n{REACT_SYSTEM_PROMPT}"

    lc_messages: List[BaseMessage] = [SystemMessage(content=augmented)]
    for m in messages:
        if m.role == "system":
            lc_messages.append(SystemMessage(content=m.content))
        elif m.role == "user":
            lc_messages.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            lc_messages.append(AIMessage(content=m.content))
    return lc_messages


async def chat_stream_with_react(
    messages: List[ChatMessage],
    llm_config: LLMConfig,
    system_prompt: SystemPrompt,
    db_tools: list,
    knowledge_source: str = "local",
    web_search: bool = False,
    web_search_api_key: Optional[str] = None,
) -> AsyncIterator[str]:
    """ReAct 深度思考模式 SSE 流。"""
    retrieve_result = _retrieve_for_messages(messages, llm_config, knowledge_source)
    session_context = build_session_context(messages)

    # 联网搜索:思考开始前强制走一遍 Tavily，把网页结果编号注入 system prompt
    # （随 SystemMessage 进入回答阶段，引用规则在两阶段都生效）。
    web_search_block = ""
    if web_search:
        yield sse_event("status", {"detail": "正在联网检索最新信息..."})
        ctx = await build_web_search_context(messages, api_key=web_search_api_key)
        web_search_block = ctx["prompt_block"]
        yield sse_event(
            "web_sources",
            {
                "query": ctx["query"],
                "status": ctx["status"],
                "sources": ctx["sources"],
                "answer_summary": ctx["answer_summary"],
                "reason": ctx.get("reason", ""),
            },
        )

    yield sse_event(
        "meta",
        {
            "provider": llm_config.provider,
            "model": llm_config.model_name,
            "runtime": "react",
            **_rag_meta(retrieve_result, session_context),
            "tools_bound": len(db_tools) + 1,  # +1 for signal_thinking_done
            "web_search": web_search,
        },
    )

    # 工具集:DB 活跃工具 + signal_thinking_done
    map_sink: List[Dict[str, Any]] = []
    event_sink: List[Tuple[str, Dict[str, Any]]] = []
    session_id = uuid.uuid4().hex
    base_tools = build_langchain_tools(
        db_tools, map_sink=map_sink, event_sink=event_sink, session_id=session_id
    )
    react_tools = [*base_tools, signal_thinking_done]
    tools_map = {t.name: t for t in react_tools}

    lc_messages = _build_lc_messages(
        messages, system_prompt, retrieve_result, session_context, web_search_block
    )
    model = create_chat_model(llm_config).bind_tools(react_tools)

    yield sse_event("thinking_start", {})

    start_ts = time.time()
    step = 0
    thinking_done = False
    thinking_summary = ""
    last_usage: Optional[dict[str, Any]] = None

    try:
        while step < MAX_THINKING_STEPS and not thinking_done:
            step += 1

            # 用非流式 ainvoke 探测工具调用:DeepSeek 等模型在「流式 + content +
            # tool_calls 混合」时会把工具调用控制 token 当文本吐出导致泄漏,
            # 非流式能拿到干净的结构化 tool_calls(与 chat_stream_with_tools 一致)。
            with llm_duration_timer(llm_config.model_name, "react_think"):
                response = await model.ainvoke(lc_messages)
            if getattr(response, "usage_metadata", None):
                last_usage = response.usage_metadata
            lc_messages.append(response)

            # 思考文本过滤掉残留控制标记后,切片回放出流式打字效果。
            think_text = _strip_tool_markup(
                _message_content_to_text(getattr(response, "content", ""))
            )
            for piece in _iter_thought_pieces(think_text):
                yield sse_event("thought", {"text": piece, "step": step})
                await asyncio.sleep(0.012)

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                # 模型没调工具,直接进入回答阶段
                yield sse_event(
                    "thought",
                    {"text": "\n(信息已足够,准备回答)", "step": step},
                )
                break

            for tc in tool_calls:
                tc_name = tc.get("name") or ""
                tc_args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                tc_id = tc.get("id") or ""

                yield sse_event(
                    "action",
                    {
                        "tool": tc_name,
                        "args": tc_args,
                        "tool_call_id": tc_id,
                        "step": step,
                    },
                )

                if tc_name == "signal_thinking_done":
                    thinking_summary = tc_args.get("summary", "") if isinstance(tc_args, dict) else ""
                    lc_messages.append(
                        ToolMessage(
                            content=json.dumps({"acknowledged": True}, ensure_ascii=False),
                            tool_call_id=tc_id,
                        )
                    )
                    yield sse_event(
                        "observation",
                        {
                            "tool": tc_name,
                            "summary": "思考阶段已结束,准备生成最终回答",
                            "tool_call_id": tc_id,
                        },
                    )
                    thinking_done = True
                    continue

                fn = tools_map.get(tc_name) or tools_map.get(tc_name.lower())
                if fn is None:
                    result_text = json.dumps(
                        {"error": f"未注册的工具:{tc_name}"}, ensure_ascii=False
                    )
                else:
                    try:
                        result = await fn.ainvoke(tc_args)
                        result_text = str(result)
                    except Exception as exc:
                        result_text = json.dumps(
                            {"error": f"{exc.__class__.__name__}: {exc}"},
                            ensure_ascii=False,
                        )

                yield sse_event(
                    "observation",
                    {
                        "tool": tc_name,
                        "summary": _summarize_observation(tc_name, result_text),
                        "tool_call_id": tc_id,
                    },
                )
                lc_messages.append(
                    ToolMessage(content=result_text, tool_call_id=tc_id)
                )

            # 工具产生的旁路事件转发给前端
            while map_sink:
                yield sse_event("map_data", map_sink.pop(0))
            while event_sink:
                evt_name, evt_payload = event_sink.pop(0)
                yield sse_event(evt_name, evt_payload)

        duration_ms = int((time.time() - start_ts) * 1000)
        if not thinking_done and step >= MAX_THINKING_STEPS and not thinking_summary:
            thinking_summary = f"已达思考步数上限 {MAX_THINKING_STEPS},基于已收集信息回答"

        yield sse_event(
            "thinking_end",
            {"duration_ms": duration_ms, "steps": step, "summary": thinking_summary},
        )

        # ===== 阶段 2:回答 =====
        answer_messages: List[BaseMessage] = [*lc_messages, SystemMessage(content=ANSWER_STAGE_PROMPT)]
        answer_model = create_chat_model(llm_config)  # 不绑定 tools
        answer_text_parts: List[str] = []
        with llm_duration_timer(llm_config.model_name, "react_answer"):
            async for chunk in answer_model.astream(answer_messages):
                usage = extract_usage_metadata(chunk)
                if usage:
                    last_usage = usage
                answer_text_parts.append(_message_content_to_text(getattr(chunk, "content", "")))

        answer_text = _strip_tool_markup("".join(answer_text_parts))
        for piece in _iter_thought_pieces(answer_text, size=18):
            if piece:
                yield sse_event("answer_chunk", {"text": piece})
                await asyncio.sleep(0.008)

        if last_usage:
            observe_llm_tokens(llm_config.model_name, last_usage)
        yield sse_event("done", {"finish_reason": "stop"})
    except Exception as exc:
        yield sse_event(
            "error",
            {"message": f"深度思考出错: {exc.__class__.__name__}: {exc}"},
        )
