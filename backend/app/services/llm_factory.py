from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.models.config import LLMConfig


def uses_mock_provider(llm_config: LLMConfig) -> bool:
    return llm_config.provider.strip().lower() == "mock" or not llm_config.api_key.strip()


def create_chat_model(llm_config: LLMConfig) -> Runnable:
    provider = llm_config.provider.strip().lower()
    common_kwargs = {"model": llm_config.model_name, "temperature": 0.7}

    if provider in {"gemini", "google", "google_genai", "google-generative-ai"}:
        return ChatGoogleGenerativeAI(
            **common_kwargs,
            google_api_key=llm_config.api_key,
        )

    kwargs = {**common_kwargs, "api_key": llm_config.api_key, "streaming": True}
    if llm_config.base_url.strip():
        kwargs["base_url"] = llm_config.base_url.strip()
    return ChatOpenAI(**kwargs)
