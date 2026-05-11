import asyncio
import json
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool as langchain_tool

from app.models.config import LLMConfig, SystemPrompt
from app.rag import get_rag_pipeline
from app.rag.schemas import RetrieveResult
from app.schemas.chat import ChatMessage
from app.services.llm_factory import create_chat_model, uses_mock_provider


def _last_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return "我想规划一次旅行。"


DESTINATION_ALIASES = {
    "冰岛": "冰岛",
    "京都": "京都",
    "东京": "东京",
    "大阪": "大阪",
    "上海": "上海",
    "海岛": "海岛",
}


def _user_messages(messages: List[ChatMessage]) -> List[str]:
    return [message.content.strip() for message in messages if message.role == "user" and message.content.strip()]


def _extract_trip_state(messages: List[ChatMessage]) -> Dict[str, Optional[str]]:
    user_texts = _user_messages(messages)
    full_text = "\n".join(user_texts)
    latest = user_texts[-1] if user_texts else ""

    destination = next((label for keyword, label in DESTINATION_ALIASES.items() if keyword in full_text), None)
    people_match = re.search(r"(\d+)\s*(个人|人|位)", full_text)
    days_match = re.search(r"(\d+)\s*(天|日)", full_text)
    budget = "中等" if "预算中等" in full_text or "中等预算" in full_text else None

    preferences = []
    for keyword in ["自然风景", "节奏慢", "轻松", "亲子", "带父母", "海边", "安静", "美食", "人文"]:
        if keyword in full_text:
            preferences.append(keyword)

    return {
        "destination": destination,
        "people": f"{people_match.group(1)}人" if people_match else None,
        "days": f"{days_match.group(1)}天" if days_match else None,
        "budget": budget,
        "preferences": "、".join(preferences) if preferences else None,
        "latest": latest,
    }


def _mock_travel_reply(messages: List[ChatMessage], system_prompt: SystemPrompt) -> str:
    state = _extract_trip_state(messages)
    destination = state["destination"] or "目的地"
    people = state["people"] or "人数待定"
    days = state["days"] or "天数待定"
    budget = state["budget"] or "预算待定"
    preferences = state["preferences"] or "旅行偏好待定"

    if state["destination"] == "冰岛":
        plan = (
            "**我先把当前信息合并一下**\n"
            f"- 目的地：冰岛\n"
            f"- 人数：{people}\n"
            f"- 预算：{budget}\n"
            f"- 偏好：{preferences}\n\n"
            "**推荐方向**\n"
            "冰岛第一次去、预算中等、想看自然风景，我会建议走南岸为主的路线：雷克雅未克作为落点，搭配黄金圈、塞里雅兰瀑布、斯科加瀑布、黑沙滩、冰川湖一线。这样景观密度高，交通也相对成熟。\n\n"
            "**人数补充后的调整**\n"
            f"如果是{people}，租车通常比纯公共交通更灵活；住宿可以优先找带厨房的公寓或小木屋，三个人分摊后更适合中等预算。冬季要保守安排车程，夏季可以把南岸拉得更完整。\n\n"
            "**我还需要确认两件事**\n"
            "1. 你计划几天？5-7 天适合经典南岸，8-10 天可以考虑更深入。\n"
            "2. 你们会自驾吗？这会直接决定路线节奏和住宿点。"
        )
        return plan

    return (
        "**我先把当前信息合并一下**\n"
        f"- 目的地：{destination}\n"
        f"- 人数：{people}\n"
        f"- 天数：{days}\n"
        f"- 预算：{budget}\n"
        f"- 偏好：{preferences}\n\n"
        "**建议方向**\n"
        "我会先按低折返、少换酒店、交通清晰的方式规划，把景点密度和休息时间平衡好。等你补充出发日期、天数和是否自驾后，我可以继续细化到每天上午、下午、晚上。\n\n"
        "**下一步**\n"
        "请告诉我出发城市、旅行天数和出行月份，我就能把路线排成更具体的一版。"
    )


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _retrieve_for_messages(messages: list[ChatMessage], llm_config: LLMConfig) -> RetrieveResult:
    return get_rag_pipeline().retrieve_context(_last_user_message(messages), llm_config=llm_config, top_k=5)


def _augmented_system_prompt(system_prompt: SystemPrompt, retrieve_result: RetrieveResult) -> str:
    if not retrieve_result.context_block:
        return system_prompt.content
    return (
        f"{system_prompt.content}\n\n"
        "## RAG Context\n"
        f"{retrieve_result.context_block}\n\n"
        f"检索路由：{', '.join(retrieve_result.analysis.routes)}；原因：{retrieve_result.analysis.reasoning}"
    )


def _to_langchain_messages(
    messages: list[ChatMessage],
    system_prompt: SystemPrompt,
    retrieve_result: RetrieveResult,
) -> list[BaseMessage]:
    langchain_messages: list[BaseMessage] = [SystemMessage(content=_augmented_system_prompt(system_prompt, retrieve_result))]
    for message in messages:
        if message.role == "system":
            langchain_messages.append(SystemMessage(content=message.content))
        elif message.role == "user":
            langchain_messages.append(HumanMessage(content=message.content))
        elif message.role == "assistant":
            langchain_messages.append(AIMessage(content=message.content))
    return langchain_messages

async def langchain_chat_stream(
    messages: list[ChatMessage],
    llm_config: LLMConfig,
    system_prompt: SystemPrompt,
) -> AsyncIterator[str]:
    retrieve_result = _retrieve_for_messages(messages, llm_config)
    yield sse_event(
        "meta",
        {
            "provider": llm_config.provider,
            "model": llm_config.model_name,
            "runtime": "langchain",
            "rag_routes": retrieve_result.analysis.routes,
            "rag_context_count": len(retrieve_result.contexts),
        },
    )

    model = create_chat_model(llm_config)
    langchain_messages = _to_langchain_messages(messages, system_prompt, retrieve_result)

    try:
        async for chunk in model.astream(langchain_messages):
            if chunk.content:
                yield sse_event("delta", {"content": chunk.content})
        yield sse_event("done", {"finish_reason": "stop"})
    except Exception as exc:
        yield sse_event("error", {"message": f"LangChain chat stream failed: {exc}"})


async def mock_chat_stream(
    messages: list[ChatMessage],
    llm_config: LLMConfig,
    system_prompt: SystemPrompt,
) -> AsyncIterator[str]:
    retrieve_result = _retrieve_for_messages(messages, llm_config)
    reply = _mock_travel_reply(messages, system_prompt)
    yield sse_event(
        "meta",
        {
            "provider": llm_config.provider,
            "model": llm_config.model_name,
            "runtime": "mock",
            "rag_routes": retrieve_result.analysis.routes,
            "rag_context_count": len(retrieve_result.contexts),
        },
    )

    for token in reply:
        yield sse_event("delta", {"content": token})
        await asyncio.sleep(0.015)

    yield sse_event("done", {"finish_reason": "stop"})


async def test_llm_connection(provider: str, model_name: str, api_key: str, base_url: str) -> dict:
    """Test an LLM configuration by sending a simple prompt."""
    from app.models.config import LLMConfig as LLMConfigModel

    temp_config = LLMConfigModel(
        provider=provider,
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
    )

    if uses_mock_provider(temp_config):
        return {"success": True, "latency_ms": 0, "message": "Mock provider: 无需测试，配置即可用"}

    model = create_chat_model(temp_config)
    start = time.time()
    try:
        response = await model.ainvoke([HumanMessage(content="回复不超过10个字：你好")])
        latency = int((time.time() - start) * 1000)
        return {"success": True, "latency_ms": latency, "message": f"连接成功（{latency}ms），返回：{response.content[:50]}"}
    except Exception as exc:
        latency = int((time.time() - start) * 1000)
        return {"success": False, "latency_ms": latency, "message": f"连接失败（{latency}ms）：{exc}"}


def _firecrawl_search_tool(tool_config: dict) -> Any:
    """Create a Firecrawl search LangChain tool."""
    api_key = tool_config.get("api_key", "")

    @langchain_tool
    def web_search(query: str) -> str:
        """Search the web for current travel information, prices, hours, reviews, and news. Use this when you need up-to-date information."""
        try:
            from firecrawl import Firecrawl
            fc = Firecrawl(api_key=api_key)
            results = fc.search(query, limit=3)
            if not results or not hasattr(results, "data") or not results.data:
                return "No search results found."
            output = []
            for item in results.data[:3]:
                title = getattr(item, "title", "")
                url = getattr(item, "url", "")
                desc = getattr(item, "description", "")
                output.append(f"- {title}\n  {url}\n  {desc}")
            return "\n".join(output)
        except Exception as e:
            return f"Web search failed: {e}"

    return web_search


def _firecrawl_scrape_tool(tool_config: dict) -> Any:
    """Create a Firecrawl scrape LangChain tool."""
    api_key = tool_config.get("api_key", "")

    @langchain_tool
    def web_scrape(url: str) -> str:
        """Extract content from a specific URL. Use this when you need detailed information from a specific webpage."""
        try:
            from firecrawl import Firecrawl
            fc = Firecrawl(api_key=api_key)
            result = fc.scrape(url, formats=["markdown"])
            if result and hasattr(result, "data") and result.data:
                return getattr(result.data, "markdown", "") or str(result.data)
            return "No content extracted."
        except Exception as e:
            return f"Web scrape failed: {e}"

    return web_scrape


TOOL_FACTORIES = {
    "firecrawl_search": _firecrawl_search_tool,
    "firecrawl_scrape": _firecrawl_scrape_tool,
}


def build_langchain_tools(tools: list) -> list[Any]:
    """Build LangChain tool functions from Tool model records."""
    langchain_tools = []
    for tool_record in tools:
        factory = TOOL_FACTORIES.get(tool_record.tool_type)
        if factory:
            import json
            try:
                config = json.loads(tool_record.config) if isinstance(tool_record.config, str) else tool_record.config
            except (json.JSONDecodeError, TypeError):
                config = {}
            langchain_tools.append(factory(config))
    return langchain_tools


async def chat_stream_with_tools(
    messages: list[ChatMessage],
    llm_config: LLMConfig,
    system_prompt: SystemPrompt,
    tools: list,
) -> AsyncIterator[str]:
    """Stream chat with tool calling support.

    Uses a two-phase approach:
    1. Non-streaming call to detect/handle tool calls
    2. Streaming call for the final response
    """
    retrieve_result = _retrieve_for_messages(messages, llm_config)
    yield sse_event(
        "meta",
        {
            "provider": llm_config.provider,
            "model": llm_config.model_name,
            "runtime": "langchain",
            "rag_routes": retrieve_result.analysis.routes,
            "rag_context_count": len(retrieve_result.contexts),
            "tools_bound": len(tools),
        },
    )

    langchain_tools_list = build_langchain_tools(tools)
    model = create_chat_model(llm_config).bind_tools(langchain_tools_list)
    langchain_messages = _to_langchain_messages(messages, system_prompt, retrieve_result)

    try:
        # Phase 1: Non-streaming to check for tool calls
        response = await model.ainvoke(langchain_messages)

        tool_rounds = 0
        tools_map = {t.name: t for t in langchain_tools_list}
        while response.tool_calls and tool_rounds < 5:
            tool_rounds += 1
            for tc in response.tool_calls:
                fn = tools_map.get(tc["name"].lower())
                if fn:
                    result = fn.invoke(tc["args"])
                    langchain_messages.append(response)
                    langchain_messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            response = await model.ainvoke(langchain_messages)

        # Phase 2: Stream the final response
        async for chunk in model.astream(langchain_messages):
            if chunk.content:
                yield sse_event("delta", {"content": chunk.content})
        yield sse_event("done", {"finish_reason": "stop"})
    except Exception as exc:
        yield sse_event("error", {"message": f"Chat with tools failed: {exc}"})


async def chat_stream(
    messages: list[ChatMessage],
    llm_config: LLMConfig,
    system_prompt: SystemPrompt,
) -> AsyncIterator[str]:
    if uses_mock_provider(llm_config):
        async for event in mock_chat_stream(messages, llm_config, system_prompt):
            yield event
        return

    async for event in langchain_chat_stream(messages, llm_config, system_prompt):
        yield event
