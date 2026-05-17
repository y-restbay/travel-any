from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.travel_tools import realtime_search_tool as rst  # noqa: E402


class _FakeTavilyClient:
    calls = 0

    def __init__(self, key=None):
        self.key = key

    async def search(self, **kwargs):
        _FakeTavilyClient.calls += 1
        return {
            "answer": "上海本周有多个音乐节和现场演出活动。",
            "results": [
                {
                    "title": "上海音乐节活动汇总",
                    "content": "近期上海音乐节活动信息,含时间、地点和票务提示。",
                    "url": "https://example.com/shanghai-music",
                    "published_date": "2026-05-13",
                }
            ],
        }


@pytest.mark.asyncio
async def test_realtime_search_success_and_cache(monkeypatch):
    rst.clear_realtime_search_cache()
    _FakeTavilyClient.calls = 0
    monkeypatch.setattr(rst, "TavilySearchClient", _FakeTavilyClient)

    args = {"query": "上海 音乐节 最近", "time_range": "week", "max_results": 5}
    first = await rst.handle_realtime_search(args, api_key="tvly-test")
    second = await rst.handle_realtime_search(args, api_key="tvly-test")

    assert first["状态"] == "success"
    assert first["查询"] == "上海 音乐节 最近"
    assert first["结果数"] == 1
    assert "来自缓存" not in first
    assert second["来自缓存"] is True
    assert _FakeTavilyClient.calls == 1


@pytest.mark.asyncio
async def test_realtime_search_validation_and_missing_key():
    rst.clear_realtime_search_cache()

    empty_query = await rst.handle_realtime_search({"query": "   "})
    assert empty_query["状态"] == "failed"
    assert "query 不能为空" in empty_query["错误"]

    missing_key = await rst.handle_realtime_search({"query": "故宫 最近 临时闭馆"})
    assert missing_key["状态"] == "failed"
    assert "TAVILY_API_KEY" in missing_key["错误"]


def test_tool_schema_and_registrations():
    from app.agents.generic_tools import build_generic_tools
    from app.services.chat_service import TOOL_FACTORIES, build_langchain_tools

    schema = rst.REALTIME_SEARCH_TOOL_SCHEMA
    assert schema["function"]["name"] == "search_realtime_travel_info"
    assert "搜索互联网获取旅游目的地" in schema["function"]["description"]
    assert "不应该调用" in schema["function"]["description"]

    assert "tavily_realtime_search" in TOOL_FACTORIES

    class _ToolRecord:
        tool_type = "tavily_realtime_search"
        config = json.dumps({"api_key": "tvly-test"})

    manual_tools = build_langchain_tools([_ToolRecord()], event_sink=[])
    assert [tool.name for tool in manual_tools] == ["search_realtime_travel_info"]

    # 联网搜索工具按设计默认不下发，仅在开关开启时进入 supervisor 工具集。
    default_names = {tool.name for tool in build_generic_tools()}
    assert "search_realtime_travel_info" not in default_names

    enabled_names = {tool.name for tool in build_generic_tools(include_web_search=True)}
    assert "search_realtime_travel_info" in enabled_names
