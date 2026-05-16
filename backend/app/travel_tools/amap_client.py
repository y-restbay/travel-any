"""高德 Web 服务 API（路径规划 v5）异步客户端。

只封装 driving / walking 两种出行方式：
- 驾车 v5：``https://restapi.amap.com/v5/direction/driving``，原生支持 1~16 个 waypoints
- 步行 v5：``https://restapi.amap.com/v5/direction/walking``，**不支持 waypoints**，多段需要由调用方分段拼接

设计要点：
- 所有错误（鉴权失败、网络超时、业务码非 0）统一以 ``{"error": "..."}`` 返回，不抛异常
- 未配置 ``AMAP_KEY`` 时进入 ``mock`` 模式：返回结构化的虚拟路径数据，本地无 key 也能完整跑通链路
- 通过 ``show_fields=cost,polyline`` 让响应里同时带 polyline 段串和 distance/duration/tolls
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HOST = "restapi.amap.com"
HTTP_TIMEOUT = 10.0


def _resolve_api_key(override: Optional[str] = None) -> str:
    if override and override.strip():
        return override.strip()
    return (os.getenv("AMAP_KEY") or "").strip()


def _resolve_host(override: Optional[str] = None) -> str:
    host = (override or os.getenv("AMAP_HOST") or DEFAULT_HOST).strip()
    return host.replace("https://", "").replace("http://", "").rstrip("/")


def is_coordinate(value: str) -> bool:
    """``lng,lat`` 形式判断；范围按高德要求：-180~180 / -90~90。"""
    if not value:
        return False
    parts = value.split(",")
    if len(parts) != 2:
        return False
    try:
        lng = float(parts[0].strip())
        lat = float(parts[1].strip())
    except ValueError:
        return False
    return -180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0


def parse_coordinate(value: str) -> Tuple[float, float]:
    """把 ``lng,lat`` 字符串解析成 ``(lng, lat)``，调用方需先用 :func:`is_coordinate` 校验。"""
    lng_str, lat_str = [p.strip() for p in value.split(",")]
    return float(lng_str), float(lat_str)


def parse_polyline(polyline: str) -> List[List[float]]:
    """高德 polyline 段串解析：``"lng,lat;lng,lat"`` → ``[[lng, lat], ...]``。"""
    points: List[List[float]] = []
    if not polyline:
        return points
    for segment in polyline.split(";"):
        if not segment.strip():
            continue
        try:
            lng_str, lat_str = segment.split(",")
            points.append([float(lng_str), float(lat_str)])
        except ValueError:
            # 单点解析失败就丢弃，不影响其余点
            continue
    return points


class AmapClient:
    """轻量异步客户端。每次实例化即可，无需复用。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        timeout: float = HTTP_TIMEOUT,
    ) -> None:
        self.api_key = _resolve_api_key(api_key)
        self.host = _resolve_host(host)
        self.timeout = timeout

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ HTTP
    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            return {"error": "未配置 AMAP_KEY，使用 mock 数据"}

        url = f"https://{self.host}{path}"
        query = {**params, "key": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=query)
        except httpx.TimeoutException:
            logger.warning("Amap request timeout: %s", url)
            return {"error": "高德地图服务超时"}
        except httpx.HTTPError as exc:
            logger.warning("Amap request failed: %s | %s", url, exc)
            return {"error": f"高德地图网络异常：{exc.__class__.__name__}"}

        if response.status_code >= 400:
            logger.warning("Amap HTTP %s: %s -> %s", response.status_code, url, response.text[:200])
            return {"error": f"高德地图返回 HTTP {response.status_code}"}

        try:
            data = response.json()
        except ValueError:
            return {"error": "高德地图返回非 JSON 数据"}

        # 高德 v5 返回 status="1" 表示成功
        status = str(data.get("status", "")).strip()
        if status and status != "1":
            info = data.get("info") or "未知错误"
            infocode = data.get("infocode") or "?"
            logger.warning("Amap business error: %s -> %s/%s", url, infocode, info)
            return {"error": f"高德地图业务错误：{info}（{infocode}）"}
        return data

    # --------------------------------------------------------------- 驾车 v5
    async def driving_directions(
        self,
        origin: str,
        destination: str,
        waypoints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """驾车路径规划。``waypoints`` 是有序坐标列表，最多 16 个。"""
        if not self.api_key:
            return _mock_directions(origin, destination, waypoints, mode="driving")

        params: Dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "show_fields": "cost,polyline",
        }
        if waypoints:
            # 高德要求多个途经点用 ; 拼接成单一字符串
            params["waypoints"] = ";".join(waypoints[:16])
        return await self._get("/v5/direction/driving", params)

    # --------------------------------------------------------------- 步行 v5
    async def walking_directions(self, origin: str, destination: str) -> Dict[str, Any]:
        """步行路径规划。原生**不支持 waypoints**，调用方需要自己分段调用并拼接。"""
        if not self.api_key:
            return _mock_directions(origin, destination, None, mode="walking")

        params: Dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "show_fields": "cost,polyline",
        }
        return await self._get("/v5/direction/walking", params)


# --------------------------------------------------------------------- mock 模式
def _mock_directions(
    origin: str,
    destination: str,
    waypoints: Optional[List[str]],
    mode: str,
) -> Dict[str, Any]:
    """没配 AMAP_KEY 时返回结构和真接口尽量一致的虚拟数据。

    polyline 用 origin → waypoints → destination 的直线串起来；distance/duration 按欧氏距离粗估。
    这样即便没 key，前端也能拿到一条折线渲染，整个链路不会断。
    """
    if not (is_coordinate(origin) and is_coordinate(destination)):
        return {"error": "mock 模式下 origin/destination 必须是 'lng,lat' 格式"}

    coords: List[Tuple[float, float]] = [parse_coordinate(origin)]
    for wp in waypoints or []:
        if is_coordinate(wp):
            coords.append(parse_coordinate(wp))
    coords.append(parse_coordinate(destination))

    # 欧氏距离 → 米：1° 经/纬 ≈ 111km，仅用于占位数字
    total_meters = 0.0
    polyline_segments: List[str] = []
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        seg_meters = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 * 111_000
        total_meters += seg_meters
        polyline_segments.append(f"{x1},{y1};{x2},{y2}")

    speed_mps = 11.0 if mode == "driving" else 1.4  # 驾车 ~40km/h，步行 ~5km/h
    duration_sec = int(total_meters / speed_mps) if speed_mps > 0 else 0
    tolls = "0"
    if mode == "driving":
        tolls = str(int(total_meters / 1000 * 0.5))  # 占位：0.5 元/km

    return {
        "status": "1",
        "info": "ok (mock)",
        "infocode": "10000",
        "_mock": True,
        "route": {
            "origin": origin,
            "destination": destination,
            "paths": [
                {
                    "distance": str(int(total_meters)),
                    "cost": {
                        "duration": str(duration_sec),
                        "tolls": tolls,
                    },
                    "steps": [
                        {
                            "instruction": f"mock segment {i + 1}",
                            "polyline": seg,
                        }
                        for i, seg in enumerate(polyline_segments)
                    ],
                }
            ],
        },
    }
