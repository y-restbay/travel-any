"""深度思考模式（ReAct）的 SSE 流式实现。

与 ``chat_stream_with_tools`` 的差异:
- 工具调用前显式输出"思考"文本,通过 ``thought`` 事件流式推给前端
- 用一个特殊工具 ``signal_thinking_done`` 标记思考阶段结束
- 思考结束后用「不带 tools」的二次调用生成最终回答,通过 ``answer_chunk`` 推送
"""

import asyncio
from datetime import date, timedelta
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool as langchain_tool

from app.models.config import LLMConfig, SystemPrompt
from app.schemas.chat import ChatMessage
from app.services.chat_service import (
    _augmented_system_prompt,
    _message_content_to_text,
    _rag_meta,
    _retrieve_for_messages,
    _user_content_with_image_ref,
    build_langchain_tools,
    sse_event,
    strip_tool_markup,
)
from app.services.llm_factory import create_chat_model
from app.services.metrics_service import (
    extract_usage_metadata,
    llm_duration_timer,
    observe_llm_tokens,
)
from app.services.react_prompts import ANSWER_STAGE_PROMPT, REACT_SYSTEM_PROMPT
from app.services.session_context_service import build_session_context
from app.services.web_search_context import WEB_SEARCH_OFF_BLOCK, build_web_search_context


MAX_THINKING_STEPS = 6
THINK_STREAM_IDLE_TIMEOUT_SECONDS = 18
THINK_STREAM_TOTAL_TIMEOUT_SECONDS = 45
THINK_STREAM_MAX_VISIBLE_CHARS = 1600
ANSWER_STREAM_IDLE_TIMEOUT_SECONDS = 20
ANSWER_STREAM_TOTAL_TIMEOUT_SECONDS = 60
ANSWER_STREAM_MAX_VISIBLE_CHARS = 7000

logger = logging.getLogger(__name__)


# DeepSeek 等模型在「content + tool_calls 混合」时会把工具调用的控制 token
# (含全角竖线 ｜U+FF5C 的特殊 token / invoke·parameter·tool_calls XML)
# 当普通文本吐出来。这里把它们从要展示的文本里抹掉,避免污染思考/回答面板。
_TOOL_MARKUP_RE = re.compile(
    r"<[^>]*｜[^>]*>"  # 含全角竖线的标签(DeepSeek 特殊 token)
    r"|</?\s*｜?｜?\s*DSML\s*｜?｜?[^>]*>"  # ｜｜DSML｜｜ 命名空间标签
    r"|</?\s*(?:invoke|parameter|tool_calls?|function_calls?)\b[^>]*>"  # 通用工具调用 XML
    r"|｜+\s*DSML\s*｜+",  # 残缺的 ｜｜DSML｜｜ 前缀(流式截断遗留)
    re.IGNORECASE,
)


def _strip_tool_markup(text: str, trim: bool = True) -> str:
    """抹掉泄漏到正文里的工具调用控制标记;顺带去掉流式截断的替换字符。

    trim=False 供流式分片使用:保留 chunk 边界换行,避免 Markdown 塌行。
    """
    if not text:
        return text
    return strip_tool_markup(_TOOL_MARKUP_RE.sub("", text).replace("�", ""), trim=trim)


# 单个工具标记的长度上限:据此设流式滞后窗口。任何被 chunk 边界切断的
# 标记,其断点都落在缓冲尾部这段窗口内,不会半截泄漏到已输出文本。
_MARKUP_TAIL_KEEP = 96


class _StreamingMarkupFilter:
    """流式增量过滤器:逐段喂入,实时吐出"可安全展示"的前缀。

    始终缓冲末尾 ``_MARKUP_TAIL_KEEP`` 个字符,因为一个工具标记可能正好
    跨在两个 chunk 边界;窗口之前的文本不含跨界半截标记,对其跑一次性的
    ``_strip_tool_markup`` 即可干净输出。``flush`` 在该轮流结束时补出尾部。
    """

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buf += text
        if len(self._buf) <= _MARKUP_TAIL_KEEP:
            return ""
        head = self._buf[:-_MARKUP_TAIL_KEEP]
        self._buf = self._buf[-_MARKUP_TAIL_KEEP:]
        return _strip_tool_markup(head, trim=False)

    def flush(self) -> str:
        out = _strip_tool_markup(self._buf, trim=False)
        self._buf = ""
        return out


def _iter_thought_pieces(text: str, size: int = 8) -> Iterator[str]:
    """把非流式拿到的思考文本切成小段,回放出"流式打字"的效果。"""
    for i in range(0, len(text), size):
        yield text[i : i + size]


@langchain_tool
def signal_thinking_done(summary: str = "") -> str:
    """当你已经通过工具调用收集到足够信息、准备给用户最终回答时,调用此工具标记思考阶段结束。

    重要:
    - 这是「深度思考模式」专用工具,调用后系统会自动切换到回答阶段
    - 即使是简单问题(例如只问天气),在拿到工具结果后也必须调用它来收尾
    - 不需要在 summary 里写完整回答,只写一句话总结接下来要回答什么即可

    参数:
    - summary: 一句话总结你将给用户什么样的回答(可选)
    """
    return json.dumps({"acknowledged": True, "summary": summary}, ensure_ascii=False)


def _summarize_observation(tool_name: str, raw_result: str) -> str:
    """从工具返回 JSON 文本提取一句话摘要给前端 observation 事件展示。"""
    try:
        data = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError):
        snippet = raw_result.strip()
        return snippet[:100] + ("…" if len(snippet) > 100 else "")

    if not isinstance(data, dict):
        return "已获取结果"

    if "error" in data:
        return f"⚠️ {data['error']}"

    if tool_name == "get_weather":
        location = data.get("地点") or data.get("location") or ""
        return f"已获取 {location} 天气" if location else "已获取天气信息"
    if tool_name == "get_directions":
        return _directions_observation_text(data)
    if tool_name == "generate_itinerary_summary":
        days = data.get("天数") or data.get("day_count") or "?"
        return f"已整合行程（{days} 天）"
    if tool_name == "export_itinerary":
        fmt = data.get("文件格式") or data.get("format") or ""
        return f"已导出{fmt or '文档'}"
    if tool_name == "search_realtime_travel_info":
        count = data.get("结果数") or len(data.get("results", []) or [])
        return f"已联网搜索 {count} 条信息"
    if tool_name in {"web_search", "web_scrape"}:
        return "已完成网页检索"
    if tool_name == "identify_landmark":
        status = data.get("状态")
        if status == "success":
            name = data.get("景点名称") or ""
            return f"已识别景点: {name}" if name else "已识别景点"
        if status == "uncertain":
            return "⚠️ 无法确定具体景点"
        if status == "failed":
            return "⚠️ 景点识别失败"

    return "已获取结果"


def _directions_observation_text(data: Dict[str, Any]) -> str:
    """把路线工具摘要转成深度思考面板里可读的多行路线。"""
    route_name = str(data.get("route_name") or "推荐路线").strip()
    mode = str(data.get("mode") or "").strip()
    mode_text = {"driving": "驾车", "walking": "步行"}.get(mode, mode)
    distance = data.get("总距离") or data.get("distance_text")
    if distance is None:
        km = data.get("distance_km")
        distance = f"{km:g} km" if isinstance(km, (int, float)) else ""
    duration = data.get("duration_text")
    if duration is None:
        minutes = data.get("duration_min")
        duration = f"{minutes} 分钟" if isinstance(minutes, (int, float)) and minutes else ""

    path_value = data.get("route_path")
    if isinstance(path_value, list):
        path = [str(item).strip() for item in path_value if str(item or "").strip()]
    else:
        path = []
    path_text = str(data.get("route_path_text") or "").strip()
    if not path_text and path:
        path_text = " → ".join(path)

    metric_bits = [bit for bit in (distance, duration) if bit]
    mode_suffix = f"（{mode_text}）" if mode_text else ""
    title = f"已规划「{route_name}」{mode_suffix}"
    if metric_bits:
        title += f"，约 {' / '.join(str(bit) for bit in metric_bits)}"

    if path_text:
        return f"{title}\n动线：{path_text}"
    stops = data.get("stops")
    if stops:
        return f"{title}\n共 {stops} 个停靠点"
    return title


# get_weather 真实返回值在 react 循环里被捕获,既用于丰富 observation 面板,
# 也在 LLM 漏填 generate_itinerary_summary 的 weather_summary 时兜底注入。
_WX_PLACEHOLDERS = {"", "-", "--", "—", "待定", "暂无", "未知", "未定", "无", "不详", "n/a", "na", "none", "null"}


def _weather_card_entries(raw_result: str) -> Tuple[str, List[Dict[str, str]]]:
    """把 get_weather 的中文键 JSON 解析成 (地点, [{date,condition,temp,tip}])。

    返回的条目结构与行程卡片 weather_summary 完全一致,可直接注入。
    """
    try:
        data = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError):
        return "", []
    if not isinstance(data, dict) or "error" in data:
        return "", []

    place = str(data.get("地点") or "").strip()
    entries: List[Dict[str, str]] = []

    now = data.get("实时")
    if isinstance(now, dict) and now.get("天气"):
        obs = str(now.get("观测时间") or "").strip()
        tip_bits = []
        if now.get("体感温度"):
            tip_bits.append(f"体感{now['体感温度']}")
        if now.get("湿度"):
            tip_bits.append(f"湿度{now['湿度']}")
        entries.append(
            {
                "date": obs[:10] if len(obs) >= 10 else "今日",
                "condition": str(now.get("天气") or "").strip(),
                "temp": str(now.get("温度") or "").strip(),
                "tip": "，".join(tip_bits),
            }
        )

    daily = data.get("逐日预报")
    if isinstance(daily, list):
        for item in daily:
            if not isinstance(item, dict):
                continue
            cond = str(item.get("白天天气") or "").strip()
            lo = str(item.get("最低温") or "").strip()
            hi = str(item.get("最高温") or "").strip()
            temp = f"{lo}~{hi}" if lo and hi else (hi or lo)
            if not cond and not temp:
                continue
            entries.append(
                {
                    "date": str(item.get("日期") or "").strip(),
                    "condition": cond,
                    "temp": temp,
                    "tip": f"紫外线{item['紫外线指数']}" if item.get("紫外线指数") else "",
                }
            )
    return place, entries


def _weather_detail_text(place: str, entries: List[Dict[str, str]]) -> str:
    """把解析后的天气条目拼成思考面板里展示的可读文本。"""
    if not entries:
        return ""
    lines: List[str] = []
    for entry in entries:
        seg = " ".join(
            part for part in (entry.get("date"), entry.get("condition"), entry.get("temp")) if part
        ).strip()
        if entry.get("tip"):
            seg += f"（{entry['tip']}）"
        if seg:
            lines.append(seg)
    if not lines:
        return ""
    return (f"{place}\n" if place else "") + "\n".join(lines)


def _weather_summary_is_empty(value: Any) -> bool:
    """LLM 传给 generate_itinerary_summary 的 weather_summary 是否缺失/全占位符。

    判定与 itinerary_tool._normalize_weather_summary 的接受条件一致:
    至少有一条带真实 condition 或 temp 才算非空。
    """
    if not isinstance(value, list) or not value:
        return True
    for item in value:
        if not isinstance(item, dict):
            continue
        cond = str(item.get("condition") or "").strip().lower()
        temp = str(item.get("temp") or "").strip().lower()
        if (cond and cond not in _WX_PLACEHOLDERS) or (temp and temp not in _WX_PLACEHOLDERS):
            return False
    return True


_PENDING_TOOL_TEXT_RE = re.compile(
    r"(现在|接下来|下一步|然后|继续|准备|开始|马上|我将|我要|需要).{0,40}"
    r"(调用|使用|执行|整合|生成|汇总|补充|完善|重新生成).{0,40}"
    r"(工具|generate_itinerary_summary|get_directions|get_weather|search_realtime_travel_info|itinerary|summary)",
    re.IGNORECASE,
)

_CN_DIGIT_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _looks_like_pending_tool_instruction(text: str) -> bool:
    """判断模型是否只是把下一步工具动作写成了自然语言。

    这种文本不能当最终答案回放，否则用户会只看到“现在调用 xxx 工具”。
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _PENDING_TOOL_TEXT_RE.search(cleaned):
        return True
    if re.search(r"(补充完整|还需要补充|需要补充|重新生成).{0,30}(行程|路线|卡片|PDF|pdf)", cleaned):
        return True
    return bool(re.fullmatch(r".{0,30}(调用|使用).{0,30}(工具|tool).{0,30}", cleaned, re.I))


def _force_tool_call_prompt(reason: str) -> str:
    return (
        "上一轮流式思考没有稳定地产出结构化工具调用，原因："
        f"{reason}。\n"
        "现在必须纠正：如果用户要求路线规划、酒店、美食、行程总结、PDF/Word 导出，"
        "不要继续输出正文或长篇思考，必须使用可用工具完成动作。"
        "通常顺序是：必要时调用 get_weather / get_directions，随后调用 "
        "generate_itinerary_summary 生成完整行程卡片；若用户要求导出，再立即调用 "
        "export_itinerary(format='pdf')。如果信息已经足够，直接调用对应工具。"
        "只有工具动作都完成后，才能调用 signal_thinking_done。"
    )


def _latest_user_text(messages: List[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content
    return ""


def _user_requested_export(messages: List[ChatMessage]) -> bool:
    text = _latest_user_text(messages).lower()
    return any(token in text for token in ("导出", "下载", "保存", "pdf", "word", "文档"))


def _cn_number_to_int(text: str) -> Optional[int]:
    value = (text or "").strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in _CN_DIGIT_MAP:
        return _CN_DIGIT_MAP[value]
    if "十" in value:
        left, _, right = value.partition("十")
        tens = _CN_DIGIT_MAP.get(left, 1) if left else 1
        ones = _CN_DIGIT_MAP.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def _extract_expected_trip_days(messages: List[ChatMessage]) -> Optional[int]:
    """从最近一条用户问题里提取明确的旅行天数,用于校验行程卡片完整性。"""
    user_text = _latest_user_text(messages)
    if not user_text:
        return None

    patterns = (
        r"(?P<num>\d{1,2})\s*(?:天|日)\s*(?:游|旅行|行程|路线|安排|玩)?",
        r"(?:玩|旅行|行程|路线|安排|规划)\s*(?P<num>\d{1,2})\s*(?:天|日)",
        r"(?P<num>[一二两三四五六七八九十]{1,3})\s*(?:天|日)\s*(?:游|旅行|行程|路线|安排|玩)?",
        r"(?:玩|旅行|行程|路线|安排|规划)\s*(?P<num>[一二两三四五六七八九十]{1,3})\s*(?:天|日)",
    )
    for pattern in patterns:
        match = re.search(pattern, user_text)
        if not match:
            continue
        days = _cn_number_to_int(match.group("num"))
        if days and 1 <= days <= 30:
            return days
    return None


def _extract_trip_start_date(messages: List[ChatMessage]) -> Optional[date]:
    """解析最近用户问题里的出发日期,支持今天/明天/后天和 YYYY-MM-DD / M月D日。"""
    user_text = _latest_user_text(messages)
    if not user_text:
        return None

    today = date.today()
    if "大后天" in user_text:
        return today + timedelta(days=3)
    if "后天" in user_text:
        return today + timedelta(days=2)
    if "明天" in user_text:
        return today + timedelta(days=1)
    if "今天" in user_text:
        return today

    match = re.search(r"(?P<year>20\d{2})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})", user_text)
    if match:
        try:
            return date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
        except ValueError:
            return None

    match = re.search(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日", user_text)
    if match:
        month = int(match.group("month"))
        day = int(match.group("day"))
        year = today.year
        try:
            parsed = date(year, month, day)
        except ValueError:
            return None
        if parsed < today - timedelta(days=7):
            try:
                parsed = date(year + 1, month, day)
            except ValueError:
                return None
        return parsed
    return None


def _trip_dates_label(start_date: Optional[date], days: Optional[int]) -> str:
    if not start_date or not days or days < 1:
        return ""
    end_date = start_date + timedelta(days=days - 1)
    return f"{start_date.isoformat()} 至 {end_date.isoformat()}"


def _current_date_prompt_block() -> str:
    today = date.today()
    return (
        "## 当前日期\n"
        f"今天是 {today.isoformat()}（Asia/Shanghai）。"
        "遇到“今天 / 明天 / 后天 / 大后天”等相对日期时，必须以这个日期为基准换算；"
        "不要臆测到其他月份。"
    )


def _count_itinerary_days_from_args(args: Dict[str, Any]) -> int:
    days = args.get("days")
    if not isinstance(days, list):
        return 0
    count = 0
    for day in days:
        if not isinstance(day, dict):
            continue
        schedule = day.get("schedule")
        if isinstance(schedule, list) and schedule:
            count += 1
    return count


def _count_itinerary_days_from_result(result_text: str, args: Dict[str, Any]) -> int:
    try:
        parsed = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        raw_count = parsed.get("天数") or parsed.get("day_count")
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return count
    return _count_itinerary_days_from_args(args)


def _is_successful_itinerary_result(result_text: str) -> bool:
    try:
        parsed = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, dict) and parsed.get("状态") == "success" and not parsed.get("error")


def _remove_incomplete_itinerary_events(
    event_sink: List[Tuple[str, Dict[str, Any]]],
    expected_days: Optional[int],
) -> None:
    if not expected_days:
        return
    kept: List[Tuple[str, Dict[str, Any]]] = []
    for evt_name, evt_payload in event_sink:
        if evt_name == "itinerary_data":
            days = evt_payload.get("days") if isinstance(evt_payload, dict) else None
            if isinstance(days, list) and len(days) < expected_days:
                continue
        kept.append((evt_name, evt_payload))
    event_sink[:] = kept


def _incomplete_itinerary_error(expected_days: int, actual_days: int) -> str:
    return json.dumps(
        {
            "error": (
                f"行程卡片不完整: 用户明确要求 {expected_days} 天, "
                f"但本次只生成了 {actual_days or 0} 天。"
            ),
            "修复要求": (
                f"必须重新调用 generate_itinerary_summary, days 数组严格生成 {expected_days} 天; "
                "每一天都要包含真实景点、酒店/住宿建议、美食/餐厅建议、交通动线和预算。"
            ),
        },
        ensure_ascii=False,
    )


def _itinerary_dates_mismatch_error(expected_dates: str, actual_dates: str) -> str:
    return json.dumps(
        {
            "error": f"行程日期不一致: 用户时间应为 {expected_dates}, 但本次生成的是 {actual_dates or '空日期'}。",
            "修复要求": f"必须重新调用 generate_itinerary_summary, trip_dates 严格填写 {expected_dates}。",
        },
        ensure_ascii=False,
    )


def _itinerary_answer_context(args: Dict[str, Any], result_text: str) -> str:
    """把行程卡片工具参数压成最终回答阶段更容易吸收的事实清单。"""
    title = str(args.get("trip_title") or "").strip()
    dates = str(args.get("trip_dates") or "").strip()
    summary = str(args.get("summary") or "").strip()
    lines: List[str] = ["### 行程卡片数据"]
    if title:
        lines.append(f"- 标题: {title}")
    if dates:
        lines.append(f"- 日期: {dates}")
    if summary:
        lines.append(f"- 概括: {summary}")

    weather = args.get("weather_summary")
    if isinstance(weather, list) and weather:
        weather_lines = []
        for item in weather[:7]:
            if not isinstance(item, dict):
                continue
            seg = " ".join(
                str(item.get(key) or "").strip()
                for key in ("date", "condition", "temp", "tip")
                if str(item.get(key) or "").strip()
            )
            if seg:
                weather_lines.append(seg)
        if weather_lines:
            lines.append("- 天气: " + "；".join(weather_lines))

    days = args.get("days")
    if isinstance(days, list):
        for index, day in enumerate(days[:8], start=1):
            if not isinstance(day, dict):
                continue
            day_no = day.get("day_number") or index
            day_title = str(day.get("title") or day.get("theme") or "").strip()
            lines.append(f"- Day {day_no}: {day_title or '当日安排'}")
            schedule = day.get("schedule")
            if isinstance(schedule, list):
                for item in schedule[:8]:
                    if not isinstance(item, dict):
                        continue
                    time_label = str(item.get("time") or "").strip()
                    place = str(item.get("place") or "").strip()
                    route = ""
                    if item.get("from") and item.get("to"):
                        route = f"{item.get('from')} → {item.get('to')}"
                    note = str(item.get("note") or item.get("tips") or "").strip()
                    cost_bits = []
                    if item.get("ticket") not in (None, ""):
                        cost_bits.append(f"门票{item.get('ticket')}元")
                    if item.get("cost") not in (None, ""):
                        cost_bits.append(f"花费{item.get('cost')}元")
                    main = place or route
                    if not main:
                        continue
                    detail = "，".join(part for part in (note, "、".join(cost_bits)) if part)
                    lines.append(f"  - {time_label} {main}" + (f": {detail}" if detail else ""))
            day_cost = day.get("day_cost")
            if isinstance(day_cost, dict) and day_cost.get("total") not in (None, ""):
                lines.append(f"  - 当日预算: {day_cost.get('total')}元")

    total_budget = args.get("total_budget")
    if isinstance(total_budget, dict) and total_budget:
        budget = "，".join(f"{key}:{value}" for key, value in total_budget.items() if value not in (None, ""))
        if budget:
            lines.append(f"- 总预算: {budget}")

    notes = args.get("important_notes")
    if isinstance(notes, list) and notes:
        note_text = "；".join(str(item).strip() for item in notes[:5] if str(item).strip())
        if note_text:
            lines.append(f"- 注意事项: {note_text}")

    try:
        result = json.loads(result_text)
        if isinstance(result, dict) and result.get("itinerary_id"):
            lines.append(f"- itinerary_id: {result['itinerary_id']}")
    except (json.JSONDecodeError, TypeError):
        pass

    return "\n".join(lines)


def _tool_answer_context(tool_name: str, tc_args: Dict[str, Any], result_text: str, observation_detail: str) -> str:
    """为最终回答阶段补一份面向答案合成的工具事实摘要。"""
    try:
        parsed = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and parsed.get("error"):
        if tool_name == "get_weather":
            return f"### 天气查询结果\n- 查询失败: {parsed['error']}\n- 最终回答不得声称已获得实时天气，只能说明天气服务暂时不可用，并给出基于常识的备选建议。"
        if tool_name == "search_realtime_travel_info":
            return f"### 联网检索结果\n- 查询失败: {parsed['error']}\n- 最终回答不得声称已完成实时联网检索。"
        return f"### 工具调用结果\n- {tool_name} 调用失败: {parsed['error']}"
    if tool_name == "get_weather" and observation_detail:
        return f"### 天气查询结果\n{observation_detail}"
    if tool_name == "get_directions":
        summary = _summarize_observation(tool_name, result_text)
        return f"### 路线规划结果\n{summary}" if summary else ""
    if tool_name == "generate_itinerary_summary":
        return _itinerary_answer_context(tc_args, result_text)
    if tool_name == "export_itinerary" and isinstance(parsed, dict):
        fmt = parsed.get("文件格式") or parsed.get("format") or "PDF"
        filename = parsed.get("文件名") or parsed.get("filename") or ""
        link = parsed.get("下载链接") or parsed.get("download_url") or ""
        return f"### 导出结果\n- 已导出: {fmt}\n- 文件: {filename}\n- 下载链接: {link}"
    if tool_name == "search_realtime_travel_info":
        summary = _summarize_observation(tool_name, result_text)
        return f"### 联网检索结果\n{summary}" if summary else ""
    if tool_name == "identify_landmark" and isinstance(parsed, dict):
        status = parsed.get("状态")
        if status == "success":
            name = parsed.get("景点名称") or ""
            city = parsed.get("所在城市") or ""
            return (
                f"### 景点识别结果\n- 识别为: {name}（{city}）\n"
                f"- 置信度: {parsed.get('置信度') or '中'}\n"
                "- 最终回答可以直接称呼这个景点名,并补充介绍/天气/周边。"
            )
        if status == "uncertain":
            features = parsed.get("图片特征") or ""
            return (
                '### 景点识别结果\n- 状态: 无法确定具体景点\n'
                f'- 观察到的视觉特征: {features}\n'
                '- 最终回答**严禁**说出具体景点名,不要写"这看起来是 XX"或"可能是 XX"等暗示。'
                '必须如实告诉用户没能识别,并礼貌询问该景点大致位置以缩小范围。'
            )
        if status == "failed":
            reason = parsed.get("错误") or "识别服务异常"
            return (
                f"### 景点识别结果\n- 状态: 识别失败 ({reason})\n"
                "- 最终回答必须如实说明识别未成功,不得编造景点名;"
                "建议请求用户重新上传或描述图片内容。"
            )
    return ""


def _split_tool_calls_for_execution(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同一轮工具可并发执行,但行程汇总必须最后跑。

    天气、搜索、路线等工具互相独立,可同时请求;generate_itinerary_summary
    依赖前面天气/路线结果和兜底注入;export_itinerary 又依赖已生成的行程。
    """
    order = {
        "generate_itinerary_summary": 1,
        "export_itinerary": 2,
        "signal_thinking_done": 3,
    }
    return sorted(
        tool_calls,
        key=lambda tc: order.get(tc.get("name") or "", 0),
    )


def _build_lc_messages(
    messages: List[ChatMessage],
    system_prompt: SystemPrompt,
    retrieve_result,
    session_context,
    web_search_block: str = "",
    available_tool_names: Optional[List[str]] = None,
) -> List[BaseMessage]:
    """在原有 system prompt 上叠加 ReAct 守则。"""
    base = _augmented_system_prompt(
        system_prompt, retrieve_result, session_context, web_search_block
    )
    if available_tool_names is None:
        available_tool_names = []
    tool_policy = (
        "## 当前可用工具\n"
        + (", ".join(sorted(available_tool_names)) if available_tool_names else "无")
        + "\n\n只能调用上面列出的工具。若某个能力对应的工具不在列表里，不要臆造工具调用；"
        "请在思考中说明该能力当前不可用，并用已有信息继续完成回答。"
    )
    augmented = f"{base}\n\n{_current_date_prompt_block()}\n\n{tool_policy}\n\n{REACT_SYSTEM_PROMPT}"

    lc_messages: List[BaseMessage] = [SystemMessage(content=augmented)]
    for m in messages:
        if m.role == "system":
            lc_messages.append(SystemMessage(content=m.content))
        elif m.role == "user":
            lc_messages.append(HumanMessage(content=_user_content_with_image_ref(m)))
        elif m.role == "assistant":
            lc_messages.append(AIMessage(content=m.content))
    return lc_messages


async def chat_stream_with_react(
    messages: List[ChatMessage],
    llm_config: LLMConfig,
    system_prompt: SystemPrompt,
    db_tools: list,
    knowledge_source: str = "local",
    web_search: bool = False,
    web_search_api_key: Optional[str] = None,
) -> AsyncIterator[str]:
    """ReAct 深度思考模式 SSE 流。"""
    yield sse_event("thinking_start", {})
    yield sse_event("status", {"detail": "正在准备深度思考..."})

    retrieve_result = _retrieve_for_messages(messages, llm_config, knowledge_source)
    session_context = build_session_context(messages)

    # 联网搜索:思考开始前强制走一遍 Tavily，把网页结果编号注入 system prompt
    # （随 SystemMessage 进入回答阶段，引用规则在两阶段都生效）。
    web_search_block = WEB_SEARCH_OFF_BLOCK
    if web_search:
        yield sse_event("status", {"detail": "正在联网检索最新信息..."})
        ctx = await build_web_search_context(messages, api_key=web_search_api_key)
        web_search_block = ctx["prompt_block"]
        yield sse_event(
            "web_sources",
            {
                "query": ctx["query"],
                "status": ctx["status"],
                "sources": ctx["sources"],
                "answer_summary": ctx["answer_summary"],
                "reason": ctx.get("reason", ""),
            },
        )

    yield sse_event(
        "meta",
        {
            "provider": llm_config.provider,
            "model": llm_config.model_name,
            "runtime": "react",
            **_rag_meta(retrieve_result, session_context),
            "tools_bound": len(db_tools) + 1,  # +1 for signal_thinking_done
            "web_search": web_search,
        },
    )

    # 工具集:DB 活跃工具 + signal_thinking_done
    map_sink: List[Dict[str, Any]] = []
    event_sink: List[Tuple[str, Dict[str, Any]]] = []
    session_id = uuid.uuid4().hex
    base_tools = build_langchain_tools(
        db_tools, map_sink=map_sink, event_sink=event_sink, session_id=session_id
    )
    react_tools = [*base_tools, signal_thinking_done]
    tools_map = {t.name: t for t in react_tools}

    lc_messages = _build_lc_messages(
        messages,
        system_prompt,
        retrieve_result,
        session_context,
        web_search_block,
        available_tool_names=list(tools_map.keys()),
    )
    model = create_chat_model(llm_config).bind_tools(react_tools)

    start_ts = time.time()
    step = 0
    thinking_done = False
    thinking_summary = ""
    direct_answer = ""  # 模型没调工具、直接产出的答案,留到回答阶段用,避免重复追问空回
    last_usage: Optional[dict[str, Any]] = None
    # get_weather 真实返回累积,LLM 漏填 generate_itinerary_summary 时兜底注入卡片
    captured_weather: List[Dict[str, str]] = []
    answer_context_blocks: List[str] = []
    expected_trip_days = _extract_expected_trip_days(messages)
    expected_trip_start = _extract_trip_start_date(messages)
    expected_trip_dates = _trip_dates_label(expected_trip_start, expected_trip_days)
    has_complete_itinerary = False

    try:
        while step < MAX_THINKING_STEPS and not thinking_done:
            step += 1

            # 真流式探测:astream 边生成边推 thought。DeepSeek 在「流式 +
            # content + tool_calls 混合」时会把工具调用控制 token 当文本吐出,
            # 用滞后窗口过滤器拦截、防止跨 chunk 截断泄漏;chunk 累加聚合出
            # 结构化 tool_calls。若 DeepSeek 把工具调用当正文吐了(astream
            # 未解析出 tool_calls 但正文带工具标记),该轮回退一次 ainvoke
            # 拿干净结构——仅泄漏轮退化为非流式,正常轮全程真流式。
            filt = _StreamingMarkupFilter()
            gathered: Optional[BaseMessage] = None
            streamed_len = 0  # 本轮真流式吐出的(已过滤)思考字符数
            used_fallback = False
            stream_interrupted_reason = ""
            tool_call_args_announced = False  # 大工具参数流式期间前端会静默几十秒
            with llm_duration_timer(llm_config.model_name, "react_think"):
                stream_iter = model.astream(lc_messages).__aiter__()
                stream_started_at = time.time()
                while True:
                    if time.time() - stream_started_at > THINK_STREAM_TOTAL_TIMEOUT_SECONDS:
                        stream_interrupted_reason = "思考阶段模型输出超过总时限"
                        logger.warning(
                            "ReAct think stream total timeout | step=%s | model=%s",
                            step,
                            llm_config.model_name,
                        )
                        break
                    if streamed_len > THINK_STREAM_MAX_VISIBLE_CHARS:
                        stream_interrupted_reason = "思考文本过长且尚未调用工具"
                        logger.warning(
                            "ReAct think stream visible text cap | step=%s | chars=%s | model=%s",
                            step,
                            streamed_len,
                            llm_config.model_name,
                        )
                        break
                    try:
                        chunk = await asyncio.wait_for(
                            stream_iter.__anext__(),
                            timeout=THINK_STREAM_IDLE_TIMEOUT_SECONDS,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        stream_interrupted_reason = "思考阶段模型长时间没有新输出"
                        logger.warning(
                            "ReAct think stream idle timeout | step=%s | model=%s",
                            step,
                            llm_config.model_name,
                        )
                        break
                    gathered = chunk if gathered is None else gathered + chunk
                    # 模型构造大工具参数(如 5 天行程的 generate_itinerary_summary)时,
                    # token 全部流到 tool_call_chunks 而非 content,前端会看到 30s+ 静默。
                    # 检测到 tool_call_chunks 首次出现就发一次状态,让用户知道在干活。
                    if not tool_call_args_announced:
                        tcc = getattr(chunk, "tool_call_chunks", None)
                        if tcc:
                            first_name = next(
                                (c.get("name") for c in tcc if isinstance(c, dict) and c.get("name")),
                                "",
                            )
                            if first_name:
                                yield sse_event(
                                    "status",
                                    {"detail": f"正在准备调用工具：{first_name}..."},
                                )
                                tool_call_args_announced = True
                    raw = _message_content_to_text(getattr(chunk, "content", ""))
                    if raw:
                        safe = filt.feed(raw)
                        if safe:
                            remaining = max(0, THINK_STREAM_MAX_VISIBLE_CHARS - streamed_len)
                            if remaining <= 0:
                                stream_interrupted_reason = "思考文本过长且尚未调用工具"
                                break
                            visible = safe[:remaining]
                            streamed_len += len(visible.strip())
                            yield sse_event("thought", {"text": visible, "step": step})
                            if len(safe) > remaining or streamed_len >= THINK_STREAM_MAX_VISIBLE_CHARS:
                                stream_interrupted_reason = "思考文本过长且尚未调用工具"
                                logger.warning(
                                    "ReAct think stream visible text cap | step=%s | chars=%s | model=%s",
                                    step,
                                    streamed_len,
                                    llm_config.model_name,
                                )
                                break
                tail = filt.flush()
                if tail and not stream_interrupted_reason:
                    remaining = max(0, THINK_STREAM_MAX_VISIBLE_CHARS - streamed_len)
                    if remaining > 0:
                        visible = tail[:remaining]
                        streamed_len += len(visible.strip())
                        yield sse_event("thought", {"text": visible, "step": step})

            response = gathered
            tool_calls = list(getattr(response, "tool_calls", None) or []) if response else []
            raw_content = (
                _message_content_to_text(getattr(response, "content", "")) if response else ""
            )
            if response is None or (not tool_calls and _TOOL_MARKUP_RE.search(raw_content)):
                used_fallback = True
                try:
                    response = await asyncio.wait_for(
                        model.ainvoke(lc_messages),
                        timeout=THINK_STREAM_IDLE_TIMEOUT_SECONDS,
                    )
                    tool_calls = list(getattr(response, "tool_calls", None) or [])
                    raw_content = _message_content_to_text(getattr(response, "content", ""))
                except asyncio.TimeoutError:
                    stream_interrupted_reason = stream_interrupted_reason or "非流式工具解析超时"
                    logger.warning(
                        "ReAct think fallback ainvoke timeout | step=%s | model=%s",
                        step,
                        llm_config.model_name,
                    )

            if stream_interrupted_reason and not tool_calls:
                lc_messages.append(AIMessage(content=_strip_tool_markup(raw_content)[:1200]))
                lc_messages.append(SystemMessage(content=_force_tool_call_prompt(stream_interrupted_reason)))
                yield sse_event(
                    "thought",
                    {
                        "text": "（思考输出过长，已停止继续展开，转为执行工具或收尾）",
                        "step": step,
                    },
                )
                continue

            usage = extract_usage_metadata(response)
            if usage:
                last_usage = usage
            lc_messages.append(response)

            think_text = _strip_tool_markup(raw_content)

            if not tool_calls:
                # 模型没调任何工具：多数情况下本轮 content 是直接答案；
                # 但有些模型会把“现在调用 generate_itinerary_summary”这类下一步
                # 工具动作写成普通文本。它不是答案，不能回放给用户。
                pending_tool_text = _looks_like_pending_tool_instruction(think_text)
                direct_answer = "" if pending_tool_text else think_text.strip()
                thinking_done = True
                thinking_summary = (
                    "工具规划已结束,准备生成最终回答"
                    if pending_tool_text
                    else "未调用工具，依据已有知识直接作答"
                )
                yield sse_event(
                    "thought",
                    {
                        "text": "（工具动作未结构化输出，转入最终回答）"
                        if pending_tool_text
                        else "（无需调用工具，直接作答）",
                        "step": step,
                    },
                )
                break

            # 有工具调用:正常轮思考文本已在上面真流式推送,这里不再回放。
            # 但 DeepSeek 把工具调用当正文吐出时本轮回退了非流式 ainvoke,
            # 真流式几乎没吐出可读思考——把清洗后的推理整段补发一次,
            # 避免深度思考面板在工具调用前空白(不伪造逐字打字)。
            if used_fallback and streamed_len < 8 and think_text:
                yield sse_event("thought", {"text": think_text, "step": step})

            ordered_tool_calls = _split_tool_calls_for_execution(tool_calls)
            tool_results: Dict[str, Tuple[str, Dict[str, Any], str]] = {}
            step_incomplete_itinerary = False

            async def invoke_tool(tc: Dict[str, Any], tc_args: Dict[str, Any]) -> str:
                tc_name = tc.get("name") or ""
                fn = tools_map.get(tc_name) or tools_map.get(tc_name.lower())
                if fn is None:
                    return json.dumps({"error": f"未注册的工具:{tc_name}"}, ensure_ascii=False)
                try:
                    result = await fn.ainvoke(tc_args)
                    return str(result)
                except Exception as exc:
                    return json.dumps(
                        {"error": f"{exc.__class__.__name__}: {exc}"},
                        ensure_ascii=False,
                    )

            def prepare_args(tc: Dict[str, Any]) -> Dict[str, Any]:
                tc_name = tc.get("name") or ""
                tc_args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                # 卡片没天气的根因:LLM 常漏填/占位 weather_summary。
                # 行程汇总工具放在本轮最后执行,因此能吃到同轮 get_weather 的真实结果。
                if (
                    tc_name == "generate_itinerary_summary"
                    and captured_weather
                    and _weather_summary_is_empty(tc_args.get("weather_summary"))
                ):
                    tc_args = {**tc_args, "weather_summary": captured_weather}
                if (
                    tc_name == "generate_itinerary_summary"
                    and expected_trip_dates
                    and str(tc_args.get("trip_dates") or "").strip() != expected_trip_dates
                ):
                    tc_args = {**tc_args, "trip_dates": expected_trip_dates}
                return tc_args

            async def flush_side_effects() -> AsyncIterator[str]:
                while map_sink:
                    yield sse_event("map_data", map_sink.pop(0))
                while event_sink:
                    evt_name, evt_payload = event_sink.pop(0)
                    yield sse_event(evt_name, evt_payload)

            async def emit_tool_result(
                tc: Dict[str, Any], tc_args: Dict[str, Any], result_text: str
            ) -> None:
                nonlocal has_complete_itinerary, step_incomplete_itinerary
                tc_name = tc.get("name") or ""
                tc_id = tc.get("id") or ""
                observation_detail = ""
                if tc_name == "get_weather":
                    place, entries = _weather_card_entries(result_text)
                    if entries:
                        seen = {e.get("date") for e in captured_weather}
                        for entry in entries:
                            if entry.get("date") and entry["date"] in seen:
                                continue
                            seen.add(entry.get("date"))
                            captured_weather.append(entry)
                        observation_detail = _weather_detail_text(place, entries)

                if tc_name == "generate_itinerary_summary":
                    actual_days = _count_itinerary_days_from_result(result_text, tc_args)
                    actual_trip_dates = str(tc_args.get("trip_dates") or "").strip()
                    if (
                        expected_trip_days
                        and _is_successful_itinerary_result(result_text)
                        and actual_days < expected_trip_days
                    ):
                        _remove_incomplete_itinerary_events(event_sink, expected_trip_days)
                        result_text = _incomplete_itinerary_error(expected_trip_days, actual_days)
                        step_incomplete_itinerary = True
                    elif (
                        expected_trip_dates
                        and _is_successful_itinerary_result(result_text)
                        and actual_trip_dates != expected_trip_dates
                    ):
                        _remove_incomplete_itinerary_events(event_sink, expected_trip_days)
                        result_text = _itinerary_dates_mismatch_error(
                            expected_trip_dates,
                            actual_trip_dates,
                        )
                        step_incomplete_itinerary = True
                    elif _is_successful_itinerary_result(result_text):
                        has_complete_itinerary = True

                answer_context = _tool_answer_context(tc_name, tc_args, result_text, observation_detail)
                if answer_context:
                    answer_context_blocks.append(answer_context)
                tool_results[tc_id] = (result_text, tc_args, observation_detail)

            runnable_calls: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
            deferred_calls: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

            for tc in ordered_tool_calls:
                tc_name = tc.get("name") or ""
                tc_args = prepare_args(tc)
                tc_id = tc.get("id") or ""

                yield sse_event(
                    "action",
                    {
                        "tool": tc_name,
                        "args": tc_args,
                        "tool_call_id": tc_id,
                        "step": step,
                    },
                )

                if tc_name == "signal_thinking_done":
                    thinking_summary = tc_args.get("summary", "") if isinstance(tc_args, dict) else ""
                    tool_results[tc_id] = (
                        json.dumps({"acknowledged": True}, ensure_ascii=False),
                        tc_args,
                        "",
                    )
                    yield sse_event(
                        "observation",
                        {
                            "tool": tc_name,
                            "summary": "思考阶段已结束,准备生成最终回答",
                            "tool_call_id": tc_id,
                        },
                    )
                    thinking_done = True
                elif tc_name in {"generate_itinerary_summary", "export_itinerary"}:
                    deferred_calls.append((tc, tc_args))
                else:
                    runnable_calls.append((tc, tc_args))

            # 第一批:天气 / 路线 / 搜索等互不依赖工具并发跑,谁先回来谁先展示。
            if runnable_calls:
                async def run_one(tc: Dict[str, Any], tc_args: Dict[str, Any]):
                    return tc, tc_args, await invoke_tool(tc, tc_args)

                tasks = [asyncio.create_task(run_one(tc, tc_args)) for tc, tc_args in runnable_calls]
                for task in asyncio.as_completed(tasks):
                    tc, tc_args, result_text = await task
                    await emit_tool_result(tc, tc_args, result_text)
                    yield sse_event(
                        "observation",
                        {
                            "tool": tc.get("name") or "",
                            "summary": _summarize_observation(tc.get("name") or "", result_text),
                            "detail": tool_results.get(tc.get("id") or "", ("", {}, ""))[2],
                            "tool_call_id": tc.get("id") or "",
                        },
                    )
                    async for event in flush_side_effects():
                        yield event

            # 第二批:行程汇总和导出依赖前面的天气/路线结果,必须最后执行。
            for tc, _tc_args in deferred_calls:
                tc_args = prepare_args(tc)
                result_text = await invoke_tool(tc, tc_args)
                await emit_tool_result(tc, tc_args, result_text)
                yield sse_event(
                    "observation",
                    {
                        "tool": tc.get("name") or "",
                        "summary": _summarize_observation(tc.get("name") or "", result_text),
                        "detail": tool_results.get(tc.get("id") or "", ("", {}, ""))[2],
                        "tool_call_id": tc.get("id") or "",
                    },
                )
                async for event in flush_side_effects():
                    yield event

            # 回写给模型时保持原始 tool_call 顺序,避免并发完成顺序影响协议语义。
            for tc in tool_calls:
                tc_id = tc.get("id") or ""
                if tc_id not in tool_results:
                    continue
                result_text, _tc_args, _detail = tool_results[tc_id]
                lc_messages.append(ToolMessage(content=result_text, tool_call_id=tc_id))

            async for event in flush_side_effects():
                yield event

            if step_incomplete_itinerary and expected_trip_days:
                thinking_done = False
                thinking_summary = ""
                lc_messages.append(
                    SystemMessage(
                        content=(
                            f"刚才的行程卡片不完整。用户明确要求 {expected_trip_days} 天完整路线规划，"
                            f"你必须继续调用 generate_itinerary_summary，days 数组严格生成 {expected_trip_days} 天。"
                            + (f"trip_dates 必须填写 {expected_trip_dates}。" if expected_trip_dates else "")
                            +
                            "每一天至少包含上午/中午/下午/晚上安排，补足酒店区域或酒店建议、美食/餐厅建议、"
                            "景点顺序、交通动线、预算和注意事项。不要只输出文字说要补充，必须结构化调用工具。"
                        )
                    )
                )
                yield sse_event(
                    "thought",
                    {
                        "text": f"（刚才的行程卡片不足 {expected_trip_days} 天，已要求重新生成完整版本）",
                        "step": step,
                    },
                )
                continue

        if (
            _user_requested_export(messages)
            and has_complete_itinerary
            and any("### 行程卡片数据" in block for block in answer_context_blocks)
            and not any("### 导出结果" in block for block in answer_context_blocks)
        ):
            yield sse_event(
                "action",
                {
                    "tool": "export_itinerary",
                    "args": {"format": "pdf"},
                    "tool_call_id": "auto_export_pdf",
                    "step": step,
                },
            )
            export_tool = tools_map.get("export_itinerary")
            if export_tool is not None:
                try:
                    export_result = await export_tool.ainvoke({"format": "pdf"})
                except Exception as exc:
                    export_result = json.dumps(
                        {"error": f"{exc.__class__.__name__}: {exc}"},
                        ensure_ascii=False,
                    )
                export_text = str(export_result)
                answer_context_blocks.append(
                    _tool_answer_context("export_itinerary", {"format": "pdf"}, export_text, "")
                    or f"### 导出结果\n{export_text[:500]}"
                )
                yield sse_event(
                    "observation",
                    {
                        "tool": "export_itinerary",
                        "summary": _summarize_observation("export_itinerary", export_text),
                        "tool_call_id": "auto_export_pdf",
                    },
                )
                while event_sink:
                    evt_name, evt_payload = event_sink.pop(0)
                    yield sse_event(evt_name, evt_payload)

        duration_ms = int((time.time() - start_ts) * 1000)
        if not thinking_done and step >= MAX_THINKING_STEPS and not thinking_summary:
            thinking_summary = f"已达思考步数上限 {MAX_THINKING_STEPS},基于已收集信息回答"

        yield sse_event(
            "thinking_end",
            {"duration_ms": duration_ms, "steps": step, "summary": thinking_summary},
        )

        # ===== 阶段 2:回答 =====
        answer_text = ""
        if direct_answer:
            # 思考阶段已直接产出答案：切片回放即可，省掉会得到空回答的二次调用。
            answer_text = direct_answer
            for piece in _iter_thought_pieces(direct_answer, size=18):
                yield sse_event("answer_chunk", {"text": piece})
                await asyncio.sleep(0.008)
        else:
            # 复用 think 阶段的 lc_messages 和 model:让 prompt cache 命中长前缀,
            # 同一份 tools 绑定也是 cache 命中的前提;ANSWER_STAGE_PROMPT 第 1 条
            # 已禁止再调工具,无需重建无 tools 的 model。
            lc_messages.append(SystemMessage(content=ANSWER_STAGE_PROMPT))
            parts: List[str] = []
            current_len = 0
            with llm_duration_timer(llm_config.model_name, "react_answer"):
                answer_iter = model.astream(lc_messages).__aiter__()
                answer_started_at = time.time()
                while True:
                    if time.time() - answer_started_at > ANSWER_STREAM_TOTAL_TIMEOUT_SECONDS:
                        logger.warning(
                            "ReAct answer stream total timeout | model=%s",
                            llm_config.model_name,
                        )
                        break
                    try:
                        chunk = await asyncio.wait_for(
                            answer_iter.__anext__(),
                            timeout=ANSWER_STREAM_IDLE_TIMEOUT_SECONDS,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.warning(
                            "ReAct answer stream idle timeout | model=%s",
                            llm_config.model_name,
                        )
                        break
                    usage = extract_usage_metadata(chunk)
                    if usage:
                        last_usage = usage
                    piece = _strip_tool_markup(
                        _message_content_to_text(getattr(chunk, "content", "")), trim=False
                    )
                    if piece:
                        remaining = max(0, ANSWER_STREAM_MAX_VISIBLE_CHARS - current_len)
                        if remaining <= 0:
                            logger.warning(
                                "ReAct answer stream visible text cap | model=%s",
                                llm_config.model_name,
                            )
                            break
                        visible = piece[:remaining]
                        parts.append(visible)
                        current_len += len(visible)
                        yield sse_event("answer_chunk", {"text": visible})
                        if len(piece) > remaining:
                            break
            answer_text = "".join(parts).strip()

        if not answer_text:
            # 兜底：二次调用没产出（模型以为已答完等），给可见收尾而非空白卡住。
            yield sse_event(
                "answer_chunk",
                {"text": thinking_summary or "抱歉，我没能给出完整回答，请换个说法再试一次。"},
            )

        if last_usage:
            observe_llm_tokens(llm_config.model_name, last_usage)
        yield sse_event("done", {"finish_reason": "stop"})
    except Exception as exc:
        yield sse_event(
            "error",
            {"message": f"深度思考出错: {exc.__class__.__name__}: {exc}"},
        )
