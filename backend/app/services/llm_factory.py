from typing import Optional

from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.models.config import LLMConfig


def uses_mock_provider(llm_config: LLMConfig) -> bool:
    return llm_config.provider.strip().lower() == "mock" or not llm_config.api_key.strip()


def create_chat_model(llm_config: LLMConfig, timeout: Optional[float] = 20.0) -> Runnable:
    provider = llm_config.provider.strip().lower()
    common_kwargs = {"model": llm_config.model_name, "temperature": 0.5}

    if provider in {"gemini", "google", "google_genai", "google-generative-ai"}:
        return ChatGoogleGenerativeAI(
            **common_kwargs,
            google_api_key=llm_config.api_key,
        )

    kwargs = {**common_kwargs, "api_key": llm_config.api_key, "streaming": True, "stream_usage": True}
    if provider in {"dashscope", "bailian", "aliyun", "aliyun-bailian"} and not llm_config.base_url.strip():
        kwargs["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    if provider in {"dashscope", "bailian", "aliyun", "aliyun-bailian"}:
        # 千问 3.x Flash 支持思考/非思考模式。聊天场景优先关闭思考,
        # 让首 token 更快,避免用户感觉“发完问题后一直没反应”。
        kwargs["extra_body"] = {"enable_thinking": False}
    if provider == "deepseek":
        # DeepSeek 的 thinking mode 在工具调用后要求把上一轮 reasoning_content
        # 原样回传；LangChain OpenAI 兼容消息目前不会稳定保留这段字段。
        # 本项目的“深度思考”由 ReAct SSE 自己展示，因此这里强制使用 chat
        # 非思考模式，避免工具调用后的第二轮请求被 DeepSeek 400 拒绝。
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    if timeout is not None:
        kwargs["timeout"] = timeout
        kwargs["max_retries"] = 0
    if llm_config.base_url.strip():
        kwargs["base_url"] = llm_config.base_url.strip()
    return ChatOpenAI(**kwargs)
