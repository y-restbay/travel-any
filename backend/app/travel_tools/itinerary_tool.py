"""行程汇总工具:把多轮工具调用收集到的天气 / 景点 / 路线整合成结构化行程。

设计要点:
- 校验只做"宽松"层次:必填字段缺失 → 返回错误;天数与 trip_dates 数量不一致 → 只警告
  (用户的真实需求 > 强一致性,LLM 偶尔会把日期写成单一字符串)
- itinerary_id 用 uuid4 hex 前 12 位,加 ``itin_`` 前缀,全局唯一
- 同时返回 (LLM 精简摘要, SSE 完整 payload),由 chat_service 调度循环把 payload 推给前端
- 写入 ITINERARY_STORE 供 export 工具读取
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.travel_tools.itinerary_store import put_itinerary

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- Tool Schema
ITINERARY_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_itinerary_summary",
            "description": (
                "当你已经通过多轮工具调用(get_weather、search_places、get_directions)收集到完整的旅行信息后,"
                "调用此工具把所有信息整合成结构化行程,推送给用户界面渲染'行程卡片'。"
                "调用前提:已有目的地、天数、每日动线、关键景点 / 餐饮 / 住宿信息。"
                "不要传空对象、占位符或只有 title/theme 的半成品;空天气和空 schedule 会被拒绝。"
                "调用后请简短总结亮点并询问用户是否需要导出 PDF / Word。"
            ),
        "parameters": {
            "type": "object",
            "properties": {
                "trip_title": {"type": "string", "description": "行程标题,如 '苏州三日游'。"},
                "trip_dates": {"type": "string", "description": "行程日期范围,如 '2026-06-01 至 2026-06-03'。"},
                "summary": {"type": "string", "description": "整段行程的一句话概括。"},
                "meta": {
                    "type": "object",
                    "description": "可选元数据:destination / people / budget / accommodation / preferences / transport_mode。",
                },
                "weather_summary": {
                    "type": "array",
                    "description": "每天天气概览,元素含 date / condition / temp / tip。只有查到真实天气时才填写,不要用 '-'、'待定'、'暂无' 这类占位符。",
                    "items": {"type": "object"},
                },
                "days": {
                    "type": "array",
                    "description": (
                        "每日安排数组(必填,且不可为空)。每项为 "
                        "{day_number:int, title:str, theme:str, schedule:[...], day_cost:{tickets,meals,transport,total}}。"
                        "schedule 是当天的时间轴,**绝不能为空**,每一项必须是对象,字段如下:"
                        "place(地点名,游览/用餐/出发类必填,如 '拙政园')、"
                        "time(时段,如 '09:00' 或 '上午')、"
                        "type(取值 depart/visit/meal/transit/return)、"
                        "note(一句话说明)、duration_min(停留分钟)、ticket(门票元)、"
                        "cost(花费元)、from/to(中转时的起讫点)、"
                        "highlights[](亮点)、must_try[](必点/必看)、cuisine(菜系)、tips(贴士)。"
                        "示例 schedule 项:"
                        '{"time":"09:00","type":"visit","place":"拙政园","duration_min":120,"ticket":90,"highlights":["远香堂","小飞虹"]}。'
                        "每天至少排 3-6 个具体地点,不要只给 title/theme 而把 schedule 留空。"
                        "没有真实地点 / 餐厅 / 交通起讫点时不要调用此工具。"
                    ),
                    "items": {"type": "object"},
                },
                "total_budget": {
                    "type": "object",
                    "description": "全程预算汇总 {tickets, meals, transport, accommodation, total}。",
                },
                "important_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 条最关键的注意事项。",
                },
            },
            "required": ["trip_title", "days"],
        },
    },
}


# --------------------------------------------------------------------- 主入口
def handle_generate_itinerary_summary(
    args: Dict[str, Any],
    *,
    session_id: str = "",
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """整合行程数据并写入缓存。

    返回 ``(summary_for_llm, sse_payload_or_none)``:
    - ``summary_for_llm``:精简结果给 LLM 用于继续对话
    - ``sse_payload``:完整行程,由调度循环推送给前端
    """
    if not isinstance(args, dict):
        return {"error": "参数必须是对象。"}, None

    trip_title = (args.get("trip_title") or "").strip()
    days_raw = args.get("days")
    if not trip_title:
        return {"error": "缺少 trip_title。"}, None
    if not isinstance(days_raw, list) or not days_raw:
        return {"error": "days 必须是非空数组。"}, None

    normalized_days = _normalize_days(days_raw)
    if not normalized_days:
        return {"error": "days 中没有任何有效的当日安排;每一天都必须包含真实地点 / 餐厅 / 交通起讫点。"}, None

    itinerary_id = "itin_" + uuid.uuid4().hex[:12]
    trip_dates = (args.get("trip_dates") or "").strip()
    notes = _safe_string_list(args.get("important_notes"))
    weather_summary = _normalize_weather_summary(args.get("weather_summary"))
    total_budget = args.get("total_budget") if isinstance(args.get("total_budget"), dict) else {}
    meta = args.get("meta") if isinstance(args.get("meta"), dict) else {}

    sse_payload: Dict[str, Any] = {
        "type": "itinerary",
        "itinerary_id": itinerary_id,
        "trip_title": trip_title,
        "trip_dates": trip_dates,
        "summary": (args.get("summary") or "").strip(),
        "meta": meta,
        "weather_summary": weather_summary,
        "days": normalized_days,
        "total_budget": total_budget,
        "important_notes": notes,
    }

    put_itinerary(itinerary_id, sse_payload, session_id=session_id)

    total_budget_value = _safe_number(total_budget.get("total")) if total_budget else None
    summary_for_llm: Dict[str, Any] = {
        "状态": "success",
        "itinerary_id": itinerary_id,
        "天数": len(normalized_days),
        "总预算": total_budget_value,
        "提示": "完整行程已在用户界面渲染,请简短总结亮点并询问用户是否需要导出 PDF 或 Word。",
    }
    return summary_for_llm, sse_payload


# --------------------------------------------------------------------- 内部
def _normalize_days(days: List[Any]) -> List[Dict[str, Any]]:
    """容错地把 days 数组归一化,并丢弃没有真实 schedule 的空壳日程。"""
    normalized: List[Dict[str, Any]] = []
    for index, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            continue
        schedule_raw = day.get("schedule")
        schedule = schedule_raw if isinstance(schedule_raw, list) else []
        normalized_schedule = _normalize_schedule(schedule)
        if not normalized_schedule:
            continue
        day_cost_raw = day.get("day_cost") if isinstance(day.get("day_cost"), dict) else {}
        normalized.append(
            {
                "day_number": _safe_int(day.get("day_number")) or index,
                "title": _clean_string(day.get("title")),
                "theme": _clean_string(day.get("theme")),
                "schedule": normalized_schedule,
                "day_cost": day_cost_raw,
            }
        )
    return normalized


def _normalize_schedule(schedule: List[Any]) -> List[Dict[str, Any]]:
    """归一化当天 schedule,过滤空对象和只有占位符的假日程。"""
    items: List[Dict[str, Any]] = []
    for item in schedule:
        if isinstance(item, dict):
            normalized = _normalize_schedule_item(item)
            if normalized:
                items.append(normalized)
        elif isinstance(item, str) and item.strip():
            place = _clean_string(item)
            if _has_meaningful_text(place):
                items.append({"place": place})
    return items


def _normalize_schedule_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    normalized: Dict[str, Any] = {}

    for key in ("time", "type", "place", "note", "from", "to", "tips", "cuisine"):
        text = _clean_string(item.get(key))
        if _has_meaningful_text(text):
            normalized[key] = text

    for key in ("highlights", "must_try"):
        values = _safe_string_list(item.get(key))
        if values:
            normalized[key] = values

    for key in ("duration_min", "cost", "ticket"):
        number = _safe_number(item.get(key))
        if number is not None:
            normalized[key] = number

    has_place = _has_meaningful_text(normalized.get("place"))
    has_route = _has_meaningful_text(normalized.get("from")) and _has_meaningful_text(normalized.get("to"))
    has_detail = any(
        [
            _has_meaningful_text(normalized.get("note")),
            _has_meaningful_text(normalized.get("tips")),
            _has_meaningful_text(normalized.get("cuisine")),
            bool(normalized.get("highlights")),
            bool(normalized.get("must_try")),
        ]
    )
    if not (has_place or has_route or has_detail):
        return None
    return normalized


def _normalize_weather_summary(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entry = {
            key: text
            for key in ("date", "condition", "temp", "tip")
            if _has_meaningful_text(text := _clean_string(item.get(key)))
        }
        has_weather_fact = _has_meaningful_text(entry.get("condition")) or _has_meaningful_text(entry.get("temp"))
        if has_weather_fact:
            entries.append(entry)
    return entries


def _safe_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [
        text
        for item in value
        if isinstance(item, (str, int, float))
        if _has_meaningful_text(text := _clean_string(item))
    ]


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


_PLACEHOLDER_TEXT = {
    "-",
    "--",
    "—",
    "n/a",
    "na",
    "none",
    "null",
    "无",
    "暂无",
    "待定",
    "未定",
    "未知",
    "不详",
}


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _has_meaningful_text(value: Any) -> bool:
    text = _clean_string(value)
    if not text:
        return False
    return text.lower() not in _PLACEHOLDER_TEXT
