"""路线规划工具：调用高德 directions，输出 LLM summary + 前端地图 payload。

设计要点：
- 同时返回两份数据：
  * ``summary``：精简文字描述，回写给 LLM 让它继续讲话
  * ``map_payload``：前端地图渲染需要的全部坐标 / 边界 / 摘要
- 错误绝不抛异常：坐标格式错、API 报错、单段失败都按结构化错误返回
- 步行 v5 不支持 waypoints：拆分为 A→B、B→C 多次调用，把 polyline 串起来。
  其中某段失败 → 该段回退为两点直线，**不影响**其它段
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from app.travel_tools.amap_client import (
    AmapClient,
    is_coordinate,
    parse_coordinate,
    parse_polyline,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------- Tool Schema
DIRECTIONS_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_directions",
        "description": (
            "规划多个地点之间的出行路线，生成可在用户界面地图区域渲染的路线数据。\n\n"
            "**触发场景**（满足任一即应主动调用）：\n"
            "1. 用户明确询问 \"怎么从 A 到 B\"、\"去 X 怎么走\"、\"路线规划\"\n"
            "2. 在推荐多个景点/餐厅/酒店后，如果用户表达了游览意图（如 \"想去\"、\"推荐几个地方玩\"、\"帮我规划\"），"
            "应在推荐后主动调用此工具，把它们串成一条路线\n"
            "3. 多日行程规划中，为每天的多个地点安排动线\n\n"
            "**不应触发的场景**：\n"
            "- 用户只询问单一信息（天气、单点开放时间等）\n"
            "- 用户只给了目的地、没有出发地——应先反问出发地\n\n"
            "调用后会为用户准备路线地图按钮，你在文字回答里需要简短提示用户 \"路线地图已准备好，点击回答下方按钮即可查看\"。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "起点坐标，'经度,纬度' 形式，例如 '120.620,31.320'。小数点后建议保留 4-6 位。",
                },
                "destination": {
                    "type": "string",
                    "description": "终点坐标，'经度,纬度' 形式。",
                },
                "waypoints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "途经点坐标数组，按顺序串起多个地点。仅驾车支持 16 个以内；"
                        "步行模式如果传了途经点，会自动分段调用并拼接。"
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["driving", "walking"],
                    "description": "出行方式。默认 driving。",
                    "default": "driving",
                },
                "route_name": {
                    "type": "string",
                    "description": "本次路线的标题，例如 '苏州一日游'、'Day 1 行程'。会显示在地图上方。",
                },
                "marker_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "可选的地点名称数组，按 [origin, ...waypoints, destination] 顺序对应。"
                        "用于地图标记的中文名展示，例如 ['拙政园', '狮子林', '寒山寺']。"
                    ),
                },
            },
            "required": ["origin", "destination"],
        },
    },
}


# --------------------------------------------------------------------- 主入口
async def handle_get_directions(
    origin: str,
    destination: str,
    waypoints: Optional[List[str]] = None,
    mode: str = "driving",
    route_name: Optional[str] = None,
    marker_names: Optional[List[str]] = None,
    *,
    client: Optional[AmapClient] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """规划路线。

    返回 ``(summary_for_llm, map_payload_or_none)``：
    - ``summary_for_llm`` 是一个 dict，回传给 LLM 让它在文字回复里复述
    - ``map_payload`` 失败时为 ``None``，成功时是给前端推送的完整结构
    """
    mode = (mode or "driving").lower().strip()
    if mode not in {"driving", "walking"}:
        return {"error": f"暂不支持的 mode: {mode}，请使用 driving 或 walking"}, None

    origin = (origin or "").strip()
    destination = (destination or "").strip()
    if not is_coordinate(origin):
        return {"error": f"origin 坐标格式错误：'{origin}'，应为 '经度,纬度'"}, None
    if not is_coordinate(destination):
        return {"error": f"destination 坐标格式错误：'{destination}'，应为 '经度,纬度'"}, None

    cleaned_waypoints: List[str] = []
    for wp in waypoints or []:
        wp_str = (wp or "").strip()
        if is_coordinate(wp_str):
            cleaned_waypoints.append(wp_str)
        else:
            logger.warning("dropping invalid waypoint: %r", wp_str)

    amap = client or AmapClient()

    if mode == "driving":
        raw = await amap.driving_directions(origin, destination, cleaned_waypoints or None)
        polyline_points, distance_m, duration_s, tolls = _extract_driving_path(raw)
    else:
        polyline_points, distance_m, duration_s, tolls = await _walking_with_waypoints(
            amap, origin, destination, cleaned_waypoints
        )
        raw = {"_mode": "walking", "_segmented": True}

    if not polyline_points:
        # 整体彻底失败：给 LLM 一个错误回执，但**不抛异常**
        err = (raw.get("error") if isinstance(raw, dict) else None) or "路径规划失败"
        return {"error": err, "mode": mode, "origin": origin, "destination": destination}, None

    markers = _build_markers(origin, cleaned_waypoints, destination, marker_names)
    bounds = _compute_bounds(polyline_points + [[lng, lat] for (_, lng, lat) in _markers_to_xy(markers)])

    distance_km = round(distance_m / 1000.0, 2) if distance_m else 0.0
    duration_min = int(round(duration_s / 60.0)) if duration_s else 0

    summary: Dict[str, Any] = {
        "mode": mode,
        "route_name": route_name or "推荐路线",
        "stops": len(markers),
        "distance_km": distance_km,
        "duration_min": duration_min,
        "tolls_yuan": tolls,
        "is_mock": bool(isinstance(raw, dict) and raw.get("_mock")),
        "tip": "路线地图已准备好，请在回复中简短提示用户点击回答下方按钮查看",
    }

    map_payload: Dict[str, Any] = {
        "type": "route",
        "route_name": route_name or "推荐路线",
        "mode": mode,
        "markers": markers,
        "polyline": polyline_points,
        "bounds": bounds,
        "summary": {
            "distance_km": distance_km,
            "duration_min": duration_min,
            "cost_yuan": tolls,
        },
    }

    return summary, map_payload


# --------------------------------------------------------------------- 解析高德响应
def _extract_driving_path(
    raw: Dict[str, Any],
) -> Tuple[List[List[float]], float, float, Optional[float]]:
    """从驾车 v5 响应里抽出 polyline / 距离 / 时长 / 过路费。

    单段失败也尽可能返回部分数据，绝不抛异常。
    """
    if not isinstance(raw, dict) or "error" in raw:
        return [], 0.0, 0.0, None

    paths = (raw.get("route") or {}).get("paths") or []
    if not paths:
        return [], 0.0, 0.0, None

    path = paths[0]
    distance_m = _safe_float(path.get("distance")) or 0.0
    cost = path.get("cost") or {}
    duration_s = _safe_float(cost.get("duration")) or 0.0
    tolls = _safe_float(cost.get("tolls"))

    points: List[List[float]] = []
    for step in path.get("steps") or []:
        polyline = step.get("polyline") or ""
        seg_points = parse_polyline(polyline)
        if not seg_points:
            continue
        # 段与段的接缝处会重复一个点，去重一次让前端更省事
        if points and seg_points and points[-1] == seg_points[0]:
            seg_points = seg_points[1:]
        points.extend(seg_points)

    return points, distance_m, duration_s, tolls


async def _walking_with_waypoints(
    amap: AmapClient,
    origin: str,
    destination: str,
    waypoints: List[str],
) -> Tuple[List[List[float]], float, float, Optional[float]]:
    """步行多段：A→W1→W2→B，分段并发调用。单段失败回退为直线连接。"""
    sequence = [origin] + list(waypoints) + [destination]
    pairs = list(zip(sequence[:-1], sequence[1:]))

    async def one(start: str, end: str) -> Tuple[List[List[float]], float, float]:
        raw = await amap.walking_directions(start, end)
        pts, dist, dur, _ = _extract_driving_path(raw)  # 步行响应结构同驾车，复用解析
        if pts:
            return pts, dist, dur
        # 单段失败：直线降级
        x1, y1 = parse_coordinate(start)
        x2, y2 = parse_coordinate(end)
        fallback_pts = [[x1, y1], [x2, y2]]
        fallback_dist = math.hypot(x2 - x1, y2 - y1) * 111_000  # 粗估
        fallback_dur = fallback_dist / 1.4
        return fallback_pts, fallback_dist, fallback_dur

    results = await asyncio.gather(*(one(a, b) for a, b in pairs))

    all_points: List[List[float]] = []
    total_dist = 0.0
    total_dur = 0.0
    for pts, dist, dur in results:
        if all_points and pts and all_points[-1] == pts[0]:
            pts = pts[1:]
        all_points.extend(pts)
        total_dist += dist
        total_dur += dur
    return all_points, total_dist, total_dur, None


# --------------------------------------------------------------------- markers / bounds
def _build_markers(
    origin: str,
    waypoints: List[str],
    destination: str,
    names: Optional[List[str]],
) -> List[Dict[str, Any]]:
    coords = [origin, *waypoints, destination]
    markers: List[Dict[str, Any]] = []
    for i, c in enumerate(coords):
        lng, lat = parse_coordinate(c)
        name = ""
        if names and i < len(names):
            name = names[i] or ""
        if not name:
            if i == 0:
                name = "起点"
            elif i == len(coords) - 1:
                name = "终点"
            else:
                name = f"途经点 {i}"
        markers.append({"name": name, "lng": lng, "lat": lat, "order": i + 1})
    return markers


def _markers_to_xy(markers: List[Dict[str, Any]]) -> List[Tuple[int, float, float]]:
    return [(m["order"], m["lng"], m["lat"]) for m in markers]


def _compute_bounds(points: List[List[float]]) -> Optional[Dict[str, List[float]]]:
    if not points:
        return None
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]
    return {
        "sw": [min(lngs), min(lats)],
        "ne": [max(lngs), max(lats)],
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
