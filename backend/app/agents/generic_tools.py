"""挂在 supervisor 上的通用工具(非 specialist 范畴的旅游能力)。

与 services/chat_service.py 里 ``TOOL_FACTORIES`` 的差异:
- 那批工具用工厂闭包持有 ``map_sink`` / ``event_sink`` 推 SSE 事件,
  因为 ``chat_stream_with_tools`` 是手写的调度循环。
- 这里在 LangGraph 中跑,使用官方的 ``get_stream_writer()`` 发自定义事件。
  外层用 ``stream_mode=["messages", "custom", "updates"]`` 接收。

工具仅在被 LangGraph 调用时存在 stream writer 上下文。若直接调用(测试)会静默忽略。
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from app.travel_tools.amap_client import AmapClient
from app.travel_tools.directions_tool import handle_get_directions
from app.travel_tools.export_tool import handle_export_itinerary
from app.travel_tools.itinerary_tool import handle_generate_itinerary_summary
from app.travel_tools.qweather_client import QWeatherClient
from app.travel_tools.realtime_search_tool import REALTIME_SEARCH_DESCRIPTION, handle_realtime_search
from app.travel_tools.weather_tool import get_weather as _get_weather


def _emit(event_name: str, payload: Dict[str, Any]) -> None:
    """在 LangGraph 上下文里推 custom 事件;没有上下文时静默。"""
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        writer({"event": event_name, "data": payload})
    except Exception:
        # 没有 stream writer(直接调用 / 测试)或 langgraph 上下文丢失
        pass


@tool(description=REALTIME_SEARCH_DESCRIPTION)
async def search_realtime_travel_info(
    query: str,
    time_range: str = "week",
    max_results: int = 5,
) -> str:
    _emit("status", {"detail": "正在联网查询最新信息..."})
    result = await handle_realtime_search(
        {"query": query, "time_range": time_range, "max_results": max_results}
    )
    return json.dumps(result, ensure_ascii=False)

@tool
async def get_weather(
    location: str,
    date_range: str = "today",
    include_hourly: bool = False,
    include_indices: bool = False,
) -> str:
    """查询某地的实时或未来天气。

    参数:
    - location: 城市或 '经度,纬度'
    - date_range: today / tomorrow / 3d / 7d
    - include_hourly / include_indices: 是否带逐小时和生活指数
    """
    client = QWeatherClient()
    try:
        result = await _get_weather(
            location=location,
            date_range=date_range,
            include_hourly=include_hourly,
            include_indices=include_indices,
            client=client,
        )
    except Exception as exc:
        result = {"error": f"天气工具异常:{exc.__class__.__name__}"}
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_directions(
    origin: str,
    destination: str,
    waypoints: Optional[List[str]] = None,
    mode: str = "driving",
    route_name: Optional[str] = None,
    marker_names: Optional[List[str]] = None,
) -> str:
    """规划路线并把地图数据推送到前端地图面板。

    - origin / destination / waypoints:'经度,纬度' 字符串
    - mode: driving / walking
    """
    client = AmapClient()
    try:
        summary, map_payload = await handle_get_directions(
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            mode=mode,
            route_name=route_name,
            marker_names=marker_names,
            client=client,
        )
    except Exception as exc:
        summary = {"error": f"路径规划异常:{exc.__class__.__name__}"}
        map_payload = None
    if map_payload is not None:
        _emit("map_data", map_payload)
    return json.dumps(summary, ensure_ascii=False)


@tool
def generate_itinerary_summary(
    trip_title: str,
    days: List[Dict[str, Any]],
    trip_dates: str = "",
    summary: str = "",
    meta: Optional[Dict[str, Any]] = None,
    weather_summary: Optional[List[Dict[str, Any]]] = None,
    total_budget: Optional[Dict[str, Any]] = None,
    important_notes: Optional[List[str]] = None,
) -> str:
    """整合天气 / 景点 / 路线为结构化行程,前端会渲染行程卡片。

    参数同 chat_service 的 tools 版本,完成多轮工具调用后调用一次。
    只有已经规划出真实地点 / 餐厅 / 交通起讫点时才调用;不要传空对象、占位符或只有 title/theme 的半成品。
    """
    args = {
        "trip_title": trip_title,
        "trip_dates": trip_dates,
        "summary": summary,
        "meta": meta or {},
        "weather_summary": weather_summary or [],
        "days": days,
        "total_budget": total_budget or {},
        "important_notes": important_notes or [],
    }
    try:
        result, payload = handle_generate_itinerary_summary(args)
    except Exception as exc:
        result = {"error": f"行程汇总异常:{exc.__class__.__name__}"}
        payload = None
    if payload is not None:
        _emit("itinerary_data", payload)
    return json.dumps(result, ensure_ascii=False)


@tool
def export_itinerary(
    itinerary_id: str,
    format: str = "pdf",
    include_map_snapshot: bool = True,
) -> str:
    """把已生成的行程导出为 PDF / Word,下载链接通过前端推送。"""
    try:
        result, payload = handle_export_itinerary(
            {
                "itinerary_id": itinerary_id,
                "format": format,
                "include_map_snapshot": include_map_snapshot,
            }
        )
    except Exception as exc:
        result = {"error": f"导出工具异常:{exc.__class__.__name__}"}
        payload = None
    if payload is not None:
        _emit("export_ready", payload)
    return json.dumps(result, ensure_ascii=False)


def build_generic_tools(
    include_web_search: bool = False,
    *,
    event_sink: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
) -> List[Any]:
    """联网搜索工具仅在开关开启时下发;默认不含,其余模式不能联网。

    ``event_sink`` 是给 Python 3.9 / LangGraph supervisor 的兼容旁路:
    ``get_stream_writer()`` 在异步工具里依赖 Python 3.11 contextvar 传播,
    老环境下可能拿不到 writer。传入 sink 后,地图/行程/导出事件会显式写入队列,
    由外层 SSE 循环转发给前端。
    """
    if event_sink is not None:
        return _build_generic_tools_with_sink(include_web_search, event_sink)

    tools: List[Any] = [
        get_weather,
        get_directions,
        generate_itinerary_summary,
        export_itinerary,
    ]
    if include_web_search:
        tools.insert(2, search_realtime_travel_info)
    return tools


def _sink_emit(
    event_sink: List[Tuple[str, Dict[str, Any]]],
    event_name: str,
    payload: Dict[str, Any],
) -> None:
    event_sink.append((event_name, payload))


def _build_generic_tools_with_sink(
    include_web_search: bool,
    event_sink: List[Tuple[str, Dict[str, Any]]],
) -> List[Any]:
    @tool(description=REALTIME_SEARCH_DESCRIPTION)
    async def search_realtime_travel_info_with_sink(
        query: str,
        time_range: str = "week",
        max_results: int = 5,
    ) -> str:
        _sink_emit(event_sink, "status", {"detail": "正在联网查询最新信息..."})
        result = await handle_realtime_search(
            {"query": query, "time_range": time_range, "max_results": max_results}
        )
        return json.dumps(result, ensure_ascii=False)

    search_realtime_travel_info_with_sink.name = "search_realtime_travel_info"

    @tool
    async def get_weather_with_sink(
        location: str,
        date_range: str = "today",
        include_hourly: bool = False,
        include_indices: bool = False,
    ) -> str:
        """查询某地的实时或未来天气。"""
        client = QWeatherClient()
        try:
            result = await _get_weather(
                location=location,
                date_range=date_range,
                include_hourly=include_hourly,
                include_indices=include_indices,
                client=client,
            )
        except Exception as exc:
            result = {"error": f"天气工具异常:{exc.__class__.__name__}"}
        return json.dumps(result, ensure_ascii=False)

    get_weather_with_sink.name = "get_weather"

    @tool
    async def get_directions_with_sink(
        origin: str,
        destination: str,
        waypoints: Optional[List[str]] = None,
        mode: str = "driving",
        route_name: Optional[str] = None,
        marker_names: Optional[List[str]] = None,
    ) -> str:
        """规划路线并把地图数据推送到前端地图面板。"""
        client = AmapClient()
        try:
            summary, map_payload = await handle_get_directions(
                origin=origin,
                destination=destination,
                waypoints=waypoints,
                mode=mode,
                route_name=route_name,
                marker_names=marker_names,
                client=client,
            )
        except Exception as exc:
            summary = {"error": f"路径规划异常:{exc.__class__.__name__}"}
            map_payload = None
        if map_payload is not None:
            _sink_emit(event_sink, "map_data", map_payload)
        return json.dumps(summary, ensure_ascii=False)

    get_directions_with_sink.name = "get_directions"

    @tool
    def generate_itinerary_summary_with_sink(
        trip_title: str,
        days: List[Dict[str, Any]],
        trip_dates: str = "",
        summary: str = "",
        meta: Optional[Dict[str, Any]] = None,
        weather_summary: Optional[List[Dict[str, Any]]] = None,
        total_budget: Optional[Dict[str, Any]] = None,
        important_notes: Optional[List[str]] = None,
    ) -> str:
        """整合天气 / 景点 / 路线为结构化行程,前端会渲染行程卡片。"""
        args = {
            "trip_title": trip_title,
            "trip_dates": trip_dates,
            "summary": summary,
            "meta": meta or {},
            "weather_summary": weather_summary or [],
            "days": days,
            "total_budget": total_budget or {},
            "important_notes": important_notes or [],
        }
        try:
            result, payload = handle_generate_itinerary_summary(args)
        except Exception as exc:
            result = {"error": f"行程汇总异常:{exc.__class__.__name__}"}
            payload = None
        if payload is not None:
            _sink_emit(event_sink, "itinerary_data", payload)
        return json.dumps(result, ensure_ascii=False)

    generate_itinerary_summary_with_sink.name = "generate_itinerary_summary"

    @tool
    def export_itinerary_with_sink(
        itinerary_id: str,
        format: str = "pdf",
        include_map_snapshot: bool = True,
    ) -> str:
        """把已生成的行程导出为 PDF / Word,下载链接通过前端推送。"""
        try:
            result, payload = handle_export_itinerary(
                {
                    "itinerary_id": itinerary_id,
                    "format": format,
                    "include_map_snapshot": include_map_snapshot,
                }
            )
        except Exception as exc:
            result = {"error": f"导出工具异常:{exc.__class__.__name__}"}
            payload = None
        if payload is not None:
            _sink_emit(event_sink, "export_ready", payload)
        return json.dumps(result, ensure_ascii=False)

    export_itinerary_with_sink.name = "export_itinerary"

    tools: List[Any] = [
        get_weather_with_sink,
        get_directions_with_sink,
        generate_itinerary_summary_with_sink,
        export_itinerary_with_sink,
    ]
    if include_web_search:
        tools.insert(2, search_realtime_travel_info_with_sink)
    return tools
