"""Tavily Search API async client wrapper for realtime travel search."""
from __future__ import annotations

import os
from typing import Optional

TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")


class TavilySearchClient:
    def __init__(self, key: Optional[str] = None):
        self.key = key or TAVILY_KEY
        if not self.key:
            raise ValueError("TAVILY_API_KEY 未配置")

        try:
            from tavily import AsyncTavilyClient
        except ImportError as exc:
            raise RuntimeError("未安装 tavily-python，请先安装依赖") from exc

        self.client = AsyncTavilyClient(api_key=self.key)

    async def search(
        self,
        query: str,
        time_range: str = "week",
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
        include_raw_content: bool = False,
    ) -> dict:
        """
        调用 Tavily 搜索。
        - include_answer=True: 返回 AI 总结的简短答案(省 token)
        - include_raw_content=False: 不返回全文,只要 snippet
        """
        return await self.client.search(
            query=query,
            time_range=time_range,
            max_results=max_results,
            search_depth=search_depth,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
        )
