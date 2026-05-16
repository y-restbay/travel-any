import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional

import httpx

from app.core.config import get_settings
from app.schemas.chat import ChatMessage
from app.services.metrics_service import llm_duration_timer, observe_llm_tokens


_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _env_file_value(*names: str) -> str:
    """Read selected keys directly from backend/.env to avoid shell env overriding app credentials."""
    if not _ENV_PATH.exists():
        return ""
    values: dict[str, str] = {}
    for line in _ENV_PATH.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    for name in names:
        value = values.get(name)
        if value:
            return value
    return ""


def _last_user_prompt(messages: List[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return "请根据知识库回答用户问题。"


def _history(messages: List[ChatMessage]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages[:-1]:
        if message.role in {"user", "assistant"} and message.content.strip():
            history.append({"role": message.role, "content": message.content.strip()})
    return history[-12:]


def _extract_text(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str):
            return text
        choices = output.get("choices")
        if isinstance(choices, list) and choices:
            message = (choices[0] or {}).get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content

    data = payload.get("Data") or payload.get("data")
    if isinstance(data, dict):
        text = data.get("Text") or data.get("text")
        if isinstance(text, str):
            return text
        choices = data.get("Choices") or data.get("choices")
        if isinstance(choices, list) and choices:
            message = (choices[0] or {}).get("Message") or (choices[0] or {}).get("message")
            if isinstance(message, dict):
                content = message.get("Content") or message.get("content")
                if isinstance(content, str):
                    return content

    return ""


def _extract_usage(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    usage = payload.get("usage") or payload.get("Usage")
    if isinstance(usage, dict):
        return usage
    data = payload.get("Data") or payload.get("data")
    if isinstance(data, dict):
        usage = data.get("Usage") or data.get("usage")
        if isinstance(usage, list) and usage:
            usage = usage[0]
        if isinstance(usage, dict):
            return usage
    return None


async def bailian_app_chat_stream(messages: List[ChatMessage]) -> AsyncIterator[str]:
    """Call a Bailian application with a DashScope sk and bridge its stream to local SSE."""
    settings = get_settings()
    api_key = (
        _env_file_value("BAILIAN_APP_API_KEY", "DASHSCOPE_API_KEY")
        or settings.bailian_app_api_key
        or settings.dashscope_api_key
        or ""
    ).strip()
    app_id = (
        _env_file_value("BAILIAN_APP_ID", "APP_ID")
        or settings.bailian_app_id
        or settings.app_id
        or ""
    ).strip()
    workspace_id = (
        _env_file_value("BAILIAN_APP_WORKSPACE_ID", "DASHSCOPE_WORKSPACE_ID")
        or settings.bailian_app_workspace_id
        or settings.dashscope_workspace_id
        or settings.bailian_workspace_id
        or ""
    ).strip()
    base_url = settings.bailian_app_base_url.rstrip("/")

    yield _sse_event(
        "meta",
        {
            "provider": "bailian_app",
            "model": app_id or "bailian-app",
            "runtime": "bailian_app",
            "rag_query": _last_user_prompt(messages),
            "rag_routes": ["cloud"],
            "rag_route_weights": {"cloud": 1.0},
            "rag_decision_source": "cloud",
            "rag_reasoning": "百炼应用负责知识库检索与回答生成，本系统透传其流式回答。",
            "rag_cloud_mode": "bailian_app",
            "rag_external_trace_available": False,
            "rag_context_count": 0,
            "rag_context_injected": False,
            "rag_context_block_preview": "",
            "rag_injected_contexts": [],
            "rag_sources": [],
        },
    )

    if not api_key or not app_id:
        yield _sse_event(
            "error",
            {
                "message": (
                    "百炼应用未配置。请在 backend/.env 设置 DASHSCOPE_API_KEY、"
                    "DASHSCOPE_WORKSPACE_ID 和 APP_ID。"
                )
            },
        )
        return

    url = f"{base_url}/apps/{app_id}/completion"
    payload: dict[str, Any] = {
        "input": {
            "prompt": _last_user_prompt(messages),
            "history": _history(messages),
        },
        "parameters": {
            "incremental_output": True,
            "result_format": "message",
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-DashScope-SSE": "enable",
    }
    if workspace_id:
        headers["X-DashScope-WorkSpace"] = workspace_id

    last_usage: Optional[dict[str, Any]] = None
    emitted_text = False
    try:
        timeout = httpx.Timeout(settings.bailian_app_timeout, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            with llm_duration_timer(app_id, "bailian_app"):
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        yield _sse_event(
                            "error",
                            {
                                "message": (
                                    f"百炼应用调用失败：HTTP {response.status_code} "
                                    f"{body.decode('utf-8', errors='ignore')[:800]}"
                                )
                            },
                        )
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        usage = _extract_usage(data)
                        if usage:
                            last_usage = usage
                        text = _extract_text(data)
                        if text:
                            emitted_text = True
                            yield _sse_event("delta", {"content": text})
                        if data.get("event") == "error" and not emitted_text:
                            yield _sse_event(
                                "error",
                                {"message": f"百炼应用调用失败：{data.get('code', 'Unknown')}: {data.get('message', '')}"},
                            )
                            return

        if last_usage:
            observe_llm_tokens(app_id, last_usage)
        yield _sse_event("done", {"finish_reason": "stop"})
    except Exception as exc:
        await asyncio.sleep(0)
        yield _sse_event("error", {"message": f"百炼应用流式调用失败：{exc.__class__.__name__}: {exc}"})
