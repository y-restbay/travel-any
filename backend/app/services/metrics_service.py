import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional

from prometheus_client import Counter, Histogram


LLM_TOKEN_USAGE_TOTAL = Counter(
    "wanderbot_llm_token_usage_total",
    "Total LLM token usage by model and token type.",
    ("model_name", "token_type"),
)

LLM_REQUESTS_TOTAL = Counter(
    "wanderbot_llm_requests_total",
    "Total LLM requests by model and runtime.",
    ("model_name", "runtime"),
)

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "wanderbot_llm_request_duration_seconds",
    "LLM request duration in seconds by model and runtime.",
    ("model_name", "runtime"),
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)


def observe_llm_tokens(model_name: str, usage: Mapping[str, Any]) -> None:
    prompt_tokens = _coerce_token_count(
        usage,
        ("prompt_tokens", "input_tokens", "prompt_token_count"),
    )
    completion_tokens = _coerce_token_count(
        usage,
        ("completion_tokens", "output_tokens", "completion_token_count"),
    )

    if prompt_tokens is not None:
        LLM_TOKEN_USAGE_TOTAL.labels(model_name=model_name, token_type="prompt").inc(prompt_tokens)
    if completion_tokens is not None:
        LLM_TOKEN_USAGE_TOTAL.labels(model_name=model_name, token_type="completion").inc(completion_tokens)


@contextmanager
def llm_duration_timer(model_name: str, runtime: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        LLM_REQUESTS_TOTAL.labels(model_name=model_name, runtime=runtime).inc()
        LLM_REQUEST_DURATION_SECONDS.labels(model_name=model_name, runtime=runtime).observe(
            time.perf_counter() - start
        )


def extract_usage_metadata(chunk: Any) -> Optional[dict[str, Any]]:
    usage = getattr(chunk, "usage_metadata", None)
    if isinstance(usage, Mapping) and usage:
        return dict(usage)

    response_metadata = getattr(chunk, "response_metadata", None)
    if isinstance(response_metadata, Mapping):
        token_usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if isinstance(token_usage, Mapping) and token_usage:
            return dict(token_usage)

    raw_usage = getattr(chunk, "usage", None)
    if isinstance(raw_usage, Mapping) and raw_usage:
        return dict(raw_usage)

    return None


def _coerce_token_count(usage: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[int]:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None
