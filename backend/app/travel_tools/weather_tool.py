"""天气查询工具：将和风天气接口的原始字段精简为中文键，回传给 LLM 使用。

设计要点（详见仓库根的 PRD/README）：
- LLM 友好：键名全部用中文短词；同一时刻的天气只保留人类关心的字段。
- 容错：所有错误（地名找不到 / 鉴权失败 / 网络超时 / 业务错误）都返回 ``{"error": "..."}``，
  绝不抛异常，因为这些信息会被回传给模型自行措辞解释给用户。
- 时间区间：``date_range`` 是 LLM 最常表达的维度，统一映射到底层不同接口的组合。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.travel_tools.qweather_client import QWeatherClient, _is_coordinate


# --------------------------------------------------------------------- Tool Schema
# OpenAI 风格的 function calling schema。LangChain 的 ``bind_tools`` 也支持等价结构，
# 但本项目里 LangChain 通过 ``@langchain_tool`` 装饰器读取函数签名，
# 该 schema 主要给 OpenAI 原生 API 或人工注册使用。
WEATHER_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "查询某个地点的实时天气或未来天气预报。"
            "用户询问某地天气、是否下雨、温度、穿衣建议、出行天气、紫外线、台风预警等情况时调用。"
            "支持中文地名（如 '三亚'）或 '经度,纬度' 形式（如 '116.41,39.92'）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "城市/地区名称或 '经度,纬度'。中文地名优先，例如 '北京'、'海南三亚'、'116.41,39.92'。",
                },
                "date_range": {
                    "type": "string",
                    "enum": ["today", "tomorrow", "3d", "7d"],
                    "description": (
                        "时间范围。today=当前实时；tomorrow=今天实时+明天预报；"
                        "3d=未来 3 天预报；7d=未来 7 天预报。默认 today。"
                    ),
                    "default": "today",
                },
                "include_hourly": {
                    "type": "boolean",
                    "description": "是否额外返回未来 24 小时逐小时数据。默认 false。",
                    "default": False,
                },
                "include_indices": {
                    "type": "boolean",
                    "description": "是否额外返回生活指数（穿衣、紫外线、运动等）。默认 false。",
                    "default": False,
                },
            },
            "required": ["location"],
        },
    },
}


# --------------------------------------------------------------------- 字段精简
def _slim_now(now: Dict[str, Any]) -> Dict[str, Any]:
    """实时天气：保留对旅行规划最有用的字段。"""
    return {
        "观测时间": now.get("obsTime"),
        "温度": _with_unit(now.get("temp"), "°C"),
        "体感温度": _with_unit(now.get("feelsLike"), "°C"),
        "天气": now.get("text"),
        "风向": now.get("windDir"),
        # windScale 在和风的语义里是 0-17 的等级（非 m/s），对中文用户更友好；
        # 题目里也明确要求 "用 windScale,不要 windSpeed"。
        "风力等级": now.get("windScale"),
        "湿度": _with_unit(now.get("humidity"), "%"),
        "过去1小时降水量": _with_unit(now.get("precip"), "mm"),
        "能见度": _with_unit(now.get("vis"), "km"),
    }


def _slim_daily(item: Dict[str, Any]) -> Dict[str, Any]:
    """逐日预报。"""
    return {
        "日期": item.get("fxDate"),
        "最高温": _with_unit(item.get("tempMax"), "°C"),
        "最低温": _with_unit(item.get("tempMin"), "°C"),
        "白天天气": item.get("textDay"),
        "夜间天气": item.get("textNight"),
        # 逐日预报里 ``precip`` 是当天总降水量。和风的 daily 没有降水概率字段，
        # 仅在逐小时预报里以 ``pop`` 给出，所以这里只保留降水量。
        "降水量": _with_unit(item.get("precip"), "mm"),
        "白天风向": item.get("windDirDay"),
        "白天风力等级": item.get("windScaleDay"),
        "夜间风向": item.get("windDirNight"),
        "夜间风力等级": item.get("windScaleNight"),
        "湿度": _with_unit(item.get("humidity"), "%"),
        "紫外线指数": item.get("uvIndex"),
        "日出": item.get("sunrise"),
        "日落": item.get("sunset"),
    }


def _slim_hourly(item: Dict[str, Any]) -> Dict[str, Any]:
    """逐小时预报。"""
    return {
        "时间": item.get("fxTime"),
        "温度": _with_unit(item.get("temp"), "°C"),
        "天气": item.get("text"),
        "降水概率": _with_unit(item.get("pop"), "%") if item.get("pop") else None,
        "降水量": _with_unit(item.get("precip"), "mm"),
        "风向": item.get("windDir"),
        "风力等级": item.get("windScale"),
        "湿度": _with_unit(item.get("humidity"), "%"),
    }


def _slim_index(item: Dict[str, Any]) -> Dict[str, Any]:
    """生活指数。"""
    return {
        "日期": item.get("date"),
        "名称": item.get("name"),
        "等级": item.get("category"),
        "建议": item.get("text"),
    }


def _slim_alert(item: Dict[str, Any]) -> Dict[str, Any]:
    """天气预警。"""
    event = item.get("eventType") or {}
    return {
        "标题": item.get("headline"),
        "事件": event.get("name") if isinstance(event, dict) else None,
        "严重程度": item.get("severity"),
        "发布机构": item.get("senderName"),
        "生效时间": item.get("effectiveTime") or item.get("onsetTime"),
        "失效时间": item.get("expireTime") or item.get("expiredTime"),
        "描述": item.get("description"),
        "防御指南": item.get("instruction"),
    }


def _with_unit(value: Any, unit: str) -> Optional[str]:
    """把和风返回的纯数字字符串补上单位，方便 LLM 直接复述。

    None/空串 → None；数值 → ``"<value><unit>"``。
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return f"{s}{unit}"


# --------------------------------------------------------------------- 主入口
async def get_weather(
    location: str,
    date_range: str = "today",
    include_hourly: bool = False,
    include_indices: bool = False,
    *,
    client: Optional[QWeatherClient] = None,
) -> Dict[str, Any]:
    """查询天气。返回结构化中文 dict，**不会抛异常**。

    返回示例（成功）::

        {
            "地点": "海南省三亚市",
            "Location ID": "101310201",
            "数据来源": "QWeather",
            "实时": {...},               # date_range == "today" 时存在
            "逐日预报": [...],            # date_range in {"tomorrow","3d","7d"}
            "逐小时预报": [...],          # include_hourly=True
            "生活指数": [...],            # include_indices=True
            "预警": [...]                # 总是返回；空数组也保留，方便 LLM 判断
        }

    返回示例（失败）::

        {"error": "未找到城市 'XYZ'，请确认地名"}
    """
    location = (location or "").strip()
    if not location:
        return {"error": "缺少 location 参数，请告诉我你想查询的城市或经纬度"}

    qclient = client or QWeatherClient()

    # ---- 1. 地名解析 -----------------------------------------------------------
    # 如果是 ``lon,lat`` 直接当 location 用；否则去 GeoAPI 查 LocationID。
    resolved_name: str
    location_id: str
    lat: Optional[float] = None
    lon: Optional[float] = None

    if _is_coordinate(location):
        lookup = await qclient.city_lookup(location)
        if "error" in lookup:
            # 坐标搜索失败也继续，因为 v7/weather/* 也能直接接受坐标
            resolved_name = location
            location_id = location
            try:
                lon_str, lat_str = [p.strip() for p in location.split(",")]
                lon = float(lon_str)
                lat = float(lat_str)
            except ValueError:
                lon = lat = None
        else:
            results = lookup.get("results") or []
            if not results:
                # 坐标没匹配到城市时也允许直接用坐标查天气
                resolved_name = location
                location_id = location
                try:
                    lon_str, lat_str = [p.strip() for p in location.split(",")]
                    lon = float(lon_str)
                    lat = float(lat_str)
                except ValueError:
                    lon = lat = None
            else:
                first = results[0]
                resolved_name = _format_location_name(first)
                # 坐标查天气更稳，避免 LocationID 在某些海外坐标上没结果
                location_id = location
                lon = _safe_float(first.get("lon"))
                lat = _safe_float(first.get("lat"))
    else:
        lookup = await qclient.city_lookup(location)
        if "error" in lookup:
            return lookup
        results = lookup.get("results") or []
        if not results:
            return {"error": f"未找到城市 '{location}'，请确认地名"}
        first = results[0]
        resolved_name = _format_location_name(first)
        location_id = str(first.get("id") or "").strip()
        lat = _safe_float(first.get("lat"))
        lon = _safe_float(first.get("lon"))
        if not location_id:
            return {"error": f"未能解析城市 '{location}' 的 Location ID"}

    # ---- 2. 并发请求各子接口 ---------------------------------------------------
    # 把所有需要的接口一起发，省往返时间。失败的接口单独处理，不影响其他数据。
    tasks: Dict[str, asyncio.Task] = {}
    tasks["now"] = asyncio.create_task(qclient.weather_now(location_id))

    if date_range in {"tomorrow", "3d"}:
        tasks["daily"] = asyncio.create_task(qclient.weather_daily(location_id, "3d"))
    elif date_range == "7d":
        tasks["daily"] = asyncio.create_task(qclient.weather_daily(location_id, "7d"))

    if include_hourly:
        tasks["hourly"] = asyncio.create_task(qclient.weather_hourly(location_id, "24h"))

    if include_indices:
        tasks["indices"] = asyncio.create_task(qclient.indices(location_id, "1d"))

    if lat is not None and lon is not None:
        tasks["alerts"] = asyncio.create_task(qclient.warning(lat, lon))

    results: Dict[str, Dict[str, Any]] = {}
    for key, task in tasks.items():
        results[key] = await task

    # ---- 3. 鉴权失败/严重错误直接短路 ------------------------------------------
    # 实时天气是必查项；如果它失败而且原因是 KEY 错误，没必要再回传其它部分。
    now_resp = results.get("now", {})
    if "error" in now_resp:
        return now_resp

    # ---- 4. 组装精简结果 -------------------------------------------------------
    output: Dict[str, Any] = {
        "地点": resolved_name,
        "Location ID": location_id,
        "数据来源": "和风天气 QWeather",
    }

    if "now" in tasks and "now" in results:
        now_data = results["now"].get("now") or {}
        if now_data:
            output["实时"] = _slim_now(now_data)

    if "daily" in tasks and "daily" in results:
        daily_resp = results["daily"]
        daily_list = (daily_resp.get("daily") or []) if "error" not in daily_resp else []
        if date_range == "tomorrow":
            # 取明天那一条：index 1（index 0 是今天）
            daily_list = daily_list[1:2]
        elif date_range == "3d":
            daily_list = daily_list[:3]
        elif date_range == "7d":
            daily_list = daily_list[:7]
        output["逐日预报"] = [_slim_daily(item) for item in daily_list]

    if "hourly" in tasks and "hourly" in results:
        hourly_resp = results["hourly"]
        hourly_list = (hourly_resp.get("hourly") or []) if "error" not in hourly_resp else []
        output["逐小时预报"] = [_slim_hourly(item) for item in hourly_list]

    if "indices" in tasks and "indices" in results:
        indices_resp = results["indices"]
        indices_list = (indices_resp.get("daily") or []) if "error" not in indices_resp else []
        output["生活指数"] = [_slim_index(item) for item in indices_list]

    # 预警：失败时返回空数组（免费订阅版可能未开放此接口）
    alerts_list: List[Dict[str, Any]] = []
    if "alerts" in tasks and "alerts" in results:
        alerts_resp = results["alerts"]
        if "error" not in alerts_resp:
            alerts_list = [_slim_alert(item) for item in (alerts_resp.get("alerts") or [])]
    output["预警"] = alerts_list

    return output


_ADM_SUFFIX = ("省", "市", "自治区", "特别行政区", "壮族自治区", "回族自治区", "维吾尔自治区")


def _strip_adm_suffix(s: str) -> str:
    """剥掉行政区划尾缀，方便判断 adm1 是不是和 name 指同一地方。"""
    s = s.strip()
    for suffix in sorted(_ADM_SUFFIX, key=len, reverse=True):
        if s.endswith(suffix) and len(s) > len(suffix):
            return s[: -len(suffix)]
    return s


def _format_location_name(loc: Dict[str, Any]) -> str:
    """把 GeoAPI 返回的 ``adm1 + adm2 + name`` 拼成完整地名。

    去重逻辑：剥掉行政尾缀后再比较——例如 adm1='北京市', name='北京' 视为同一地点，
    最终输出 '北京市' 而不是叠词 '北京市北京'。
    """
    name = (loc.get("name") or "").strip()
    adm1 = (loc.get("adm1") or "").strip()
    adm2 = (loc.get("adm2") or "").strip()
    country = (loc.get("country") or "").strip()

    parts: List[str] = []
    name_core = _strip_adm_suffix(name)
    adm1_core = _strip_adm_suffix(adm1)
    adm2_core = _strip_adm_suffix(adm2)

    if adm1 and adm1_core != name_core:
        parts.append(adm1)
    if adm2 and adm2_core != adm1_core and adm2_core != name_core:
        parts.append(adm2)
    parts.append(name)
    out = "".join(parts)
    # 非中国地区把国家名加在最前，便于 LLM 复述
    if country and country != "中国" and country not in out:
        out = f"{country} {out}"
    return out


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------- 手动测试
if __name__ == "__main__":
    # 用法：在仓库根执行 ``python -m app.travel_tools.weather_tool``（确保 QWEATHER_KEY 已设置）。
    import json

    async def _main() -> None:
        cases = [
            {"location": "北京", "date_range": "today"},
            {"location": "上海", "date_range": "7d", "include_indices": True},
            {"location": "116.41,39.92", "date_range": "tomorrow"},
            {"location": "不存在的地名XYZ", "date_range": "today"},
        ]
        for case in cases:
            print(f"\n=== {case} ===")
            result = await get_weather(**case)
            print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])

    asyncio.run(_main())
