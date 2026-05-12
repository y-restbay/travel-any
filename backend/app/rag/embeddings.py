import hashlib
import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from app.core.config import Settings
from app.models.config import EmbeddingConfig


LATIN_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+", re.UNICODE)
CJK_SEQUENCE_PATTERN = re.compile(r"[\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    lowered = text.lower()
    tokens = LATIN_TOKEN_PATTERN.findall(lowered)
    for sequence in CJK_SEQUENCE_PATTERN.findall(lowered):
        if len(sequence) == 1:
            continue
        tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
        if len(sequence) >= 3:
            tokens.extend(sequence[index : index + 3] for index in range(len(sequence) - 2))
    if tokens:
        return tokens
    return [char for char in lowered if not char.isspace()]


class HashEmbeddingFunction:
    """Deterministic local embeddings so RAG works without external API keys."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def __call__(self, input: Iterable[str]) -> List[List[float]]:
        return self.embed_documents(list(input))

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    collection_name: str
    is_real_embedding: bool


class LangChainEmbeddingFunction:
    """Thin adapter so LangChain embedding models can be used with Chroma directly."""

    def __init__(self, embeddings, profile: EmbeddingProfile) -> None:
        self.embeddings = embeddings
        self.profile = profile

    def __call__(self, input: Iterable[str]) -> List[List[float]]:
        return self.embed_documents(list(input))

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.embeddings.embed_query(text)


def _safe_collection_suffix(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower()).strip("_")
    return cleaned[:48] or "default"


def _collection_name(provider: str, model: str) -> str:
    raw = f"{provider}:{model}"
    digest = hashlib.blake2b(raw.encode("utf-8"), digest_size=5).hexdigest()
    readable = _safe_collection_suffix(f"{provider}_{model}")[:36]
    return f"wanderbot_knowledge_{readable}_{digest}"[:63].strip("_-")


def _hash_profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        provider="hash",
        model="hash-384",
        collection_name="wanderbot_knowledge",
        is_real_embedding=False,
    )


def create_embedding_function(settings: Settings, db_config: Optional[EmbeddingConfig] = None):
    provider = (db_config.provider if db_config is not None else settings.rag_embedding_provider).strip().lower()
    model_name = (db_config.model_name if db_config is not None else settings.rag_embedding_model).strip()
    api_key = (db_config.api_key if db_config is not None else settings.rag_embedding_api_key or "").strip()
    base_url = (db_config.base_url if db_config is not None else settings.rag_embedding_base_url or "").strip()

    if provider in {"openai", "openai-compatible", "deepseek", "siliconflow", "dashscope"} and api_key:
        from langchain_openai import OpenAIEmbeddings

        model = model_name or "text-embedding-3-large"
        kwargs = {
            "model": model,
            "api_key": api_key,
            "timeout": settings.rag_embedding_timeout,
            "max_retries": 1,
        }
        if base_url:
            kwargs["base_url"] = base_url
        profile = EmbeddingProfile(
            provider=provider,
            model=model,
            collection_name=_collection_name(provider, model),
            is_real_embedding=True,
        )
        return LangChainEmbeddingFunction(OpenAIEmbeddings(**kwargs), profile)

    if provider in {"gemini", "google", "google_genai", "google-generative-ai"} and api_key:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        model = model_name or "models/gemini-embedding-001"
        profile = EmbeddingProfile(
            provider="gemini",
            model=model,
            collection_name=_collection_name("gemini", model),
            is_real_embedding=True,
        )
        return LangChainEmbeddingFunction(
            GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key),
            profile,
        )

    profile = _hash_profile()
    return LangChainEmbeddingFunction(HashEmbeddingFunction(), profile)
