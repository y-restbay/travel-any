"""Realtime travel search tool backed by Tavily."""
from __future__ import annotations

import copy
import hashlib
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .tavily_client import TavilySearchClient

# 简单内存缓存,生产环境替换为 Redis
_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 30 * 60  # 30 分钟


def _cache_key(query: str, time_range: str, max_results: int) -> str:
    raw = f"{query}|{time_range}|{max_results}"
    return hashlib.md5(raw.encode()).hexdigest()


REALTIME_SEARCH_DESCRIPTION = """搜索互联网获取旅游目的地、景点、城市的**最新实时信息**。

【何时应该调用】
1. **时效性问题**:答案会随时间变化,且用户关心当下状态
   - 景区临时闭馆、限流、维护通知
   - 节庆活动、展览、演出排期
   - 道路施工、交通管制
   - 签证签注政策最新变化
   - 突发事件对旅游的影响

2. **训练数据可能过时的问题**
   - "这个月""上周""最近"开业/关闭的地方
   - 近期网红打卡地
   - 今年的活动安排

3. **用户明确要求验证或了解最新情况**
   - 包含"最近""目前""现在""今年""这个月"等时间词
   - "还开放吗""还在办吗"等状态确认
   - "听说...""真的吗"等验证类提问

【何时不应该调用】
1. **有专用工具可解决**:
   - 天气查询 → 用 get_weather
   - 地点/餐厅/酒店查询 → 用 search_places / search_hotels
   - 路线规划 → 用 get_directions
   ❌ 不要用搜索代替这些专用工具

2. **稳定的常识/历史/文化信息**
   - "故宫的历史""长城在哪""苏州园林特色"
   - 这些训练数据足够,搜索反而引入噪音

3. **主观推荐和开放问题**
   - "哪里好玩""推荐去哪"——这是规划,不是查信息
   - 用 search_places 拿候选 + 自己组织回答

【参数填写要求】
- query 要具体,带上**地点 + 时间 + 主题**三要素
  ✅ "三亚 海棠湾 2026年5月 开放"
  ❌ "三亚信息"
- 涉及当下状态用 time_range="day" 或 "week"
- 政策类用 "month",较稳定的查询用 "year"

【回答时的责任】
使用本工具结果回答时,必须:
- 在回答中说明"根据网络最新信息..."或"据 XX 报道..."
- 末尾标注 1-3 个信息来源链接
- 对可能变化的信息提醒"建议出行前再次确认"
"""


REALTIME_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_realtime_travel_info",
        "description": REALTIME_SEARCH_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "具体搜索关键词,必须包含地点、时间和主题,如'故宫 2026年5月 临时闭馆'。",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "default": "week",
                    "description": "搜索时间范围: day=突发/当日, week=近期活动/临时变化, month=政策更新, year=较稳定更新。",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                    "description": "返回结果数,范围 1-10。",
                },
            },
            "required": ["query"],
        },
    },
}


def clear_realtime_search_cache() -> None:
    _CACHE.clear()


def _safe_max_results(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 5
    return min(max(parsed, 1), 10)


async def handle_realtime_search(args: Dict[str, Any], *, api_key: Optional[str] = None) -> dict:
    query = str(args.get("query", "")).strip()
    time_range = str(args.get("time_range", "week")).strip()
    max_results = _safe_max_results(args.get("max_results", 5))

    # 参数校验
    if not query:
        return {
            "状态": "failed",
            "错误": "query 不能为空",
            "建议": "请提供具体的搜索关键词,包含地点和时间",
        }

    if time_range not in ("day", "week", "month", "year"):
        time_range = "week"

    # 缓存检查
    key = _cache_key(query, time_range, max_results)
    if key in _CACHE:
        cached_at, cached_data = _CACHE[key]
        if time.time() - cached_at < CACHE_TTL:
            result = copy.deepcopy(cached_data)
            result["来自缓存"] = True
            return result

    # 调用 Tavily
    try:
        client = TavilySearchClient(key=api_key)
        raw = await client.search(
            query=query,
            time_range=time_range,
            max_results=max_results,
        )
    except Exception as e:
        return {
            "状态": "failed",
            "错误": f"搜索服务异常: {str(e)}",
            "建议": "请告知用户搜索功能暂时不可用,基于已知信息回答",
        }

    # 质量过滤:按 Tavily 相关度排序 → 同域名去重 → 丢弃明显跑题的低分结果
    # (但有强结果时才丢,避免全部低分时返回空)
    results_raw = raw.get("results", []) or []
    seen_domains: set[str] = set()
    deduped = []
    for r in sorted(results_raw, key=lambda x: x.get("score", 0) or 0, reverse=True):
        domain = urlparse(r.get("url", "") or "").netloc.lower()
        if domain and domain in seen_domains:
            continue
        seen_domains.add(domain)
        deduped.append(r)
    strong = [r for r in deduped if (r.get("score", 0) or 0) >= 0.4]
    final = (strong if len(strong) >= 2 else deduped)[:max_results]

    # 精简返回结构
    result = {
        "状态": "success",
        "查询": query,
        "时效范围": time_range,
        "AI摘要": raw.get("answer", ""),
        "结果数": len(final),
        "结果": [
            {
                "标题": r.get("title", ""),
                "摘要": (r.get("content", "") or "")[:800],
                "链接": r.get("url", ""),
                "发布时间": r.get("published_date", "未知"),
                "相关度": round(r.get("score", 0) or 0, 3),
            }
            for r in final
        ],
        "使用提示": "请在回答中引用来源,提醒用户出行前再次确认",
    }

    # 写入缓存
    _CACHE[key] = (time.time(), copy.deepcopy(result))

    return result
