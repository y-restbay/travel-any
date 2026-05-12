# WanderBot Backend

FastAPI + SQLite backend for the WanderBot V1 travel assistant.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 6688
```

API docs: http://127.0.0.1:6688/docs

## RAG Embeddings

By default the local prototype uses deterministic hash embeddings so it can run without external keys.
For production-quality retrieval, configure a real embedding provider in `.env`:

```bash
RAG_EMBEDDING_PROVIDER=openai
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_API_KEY=sk-...
```

OpenAI-compatible embedding endpoints can also set `RAG_EMBEDDING_BASE_URL`.
Gemini embeddings can use:

```bash
RAG_EMBEDDING_PROVIDER=gemini
RAG_EMBEDDING_MODEL=models/gemini-embedding-001
RAG_EMBEDDING_API_KEY=...
```

After switching embedding providers or models, rebuild the vector index from the admin knowledge base page, or call:

```bash
curl -X POST http://127.0.0.1:6688/api/rag/rebuild-vector-index
```

## 天气工具（QWeather）

`app/travel_tools/` 提供基于和风天气的 `get_weather` 工具，LLM 可在用户询问天气、出行、穿衣建议时调用。

### 配置

在 `.env` 中加入：

```bash
QWEATHER_KEY=你的和风KEY        # 必填，在 https://console.qweather.com 申请
# QWEATHER_HOST=devapi.qweather.com      # 可选，默认即此值
# QWEATHER_GEO_HOST=geoapi.qweather.com  # 可选，默认即此值
```

### 注册到工具表

工具系统通过数据库 `tools` 表管理，启动后通过管理端 `/admin/tools` 创建一条 `tool_type=qweather_weather` 的记录即可启用。

也可以直接调用接口创建：

```bash
curl -X POST http://127.0.0.1:6688/api/admin/tools \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "get_weather",
    "label": "Weather (QWeather)",
    "description": "查询任意城市的实时天气或未来 3/7 天预报，可选生活指数与逐小时数据。用户询问某地天气、是否下雨、穿衣建议、出行天气时使用。",
    "tool_type": "qweather_weather",
    "config": {"api_key": "", "weather_host": "", "geo_host": ""},
    "is_active": true
  }'
```

`config.api_key` 留空表示从环境变量 `QWEATHER_KEY` 读取，填写则覆盖之。预设也可通过 `GET /api/admin/tools/presets` 拿到（`name=get_weather`）。

### 手动验证

```bash
cd backend && source .venv/bin/activate
export QWEATHER_KEY=...
python -m app.travel_tools.weather_tool
```
