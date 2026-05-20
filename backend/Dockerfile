# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    DATABASE_URL=sqlite:////data/wanderbot.db \
    RAG_CHROMA_PATH=/data/storage/chroma \
    RAG_BM25_PATH=/data/storage/bm25_index.json \
    EXPORT_DIR=/data/storage/exports

WORKDIR /app

RUN adduser \
        --disabled-password \
        --gecos "" \
        --home "/nonexistent" \
        --shell "/usr/sbin/nologin" \
        --no-create-home \
        --uid 10001 \
        appuser \
    && mkdir -p /data/storage/exports \
    && chown -R appuser:appuser /data

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY --chown=appuser:appuser app ./app

USER appuser

EXPOSE 6688

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6688/api/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "6688", "--proxy-headers"]
