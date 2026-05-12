"""和风天气（QWeather）异步 HTTP 客户端。

封装了城市搜索、实时天气、逐日预报、逐小时预报、生活指数、预警等接口的调用，
负责：
- 拼接 URL 与查询参数；
- 用 ``X-QW-Api-Key`` 请求头传递 API Key（兼容免费订阅版的旧公共域名）；
- 超时与异常的结构化包装：调用方只需检查返回 dict 中的 ``error`` 字段。

注意：
- 和风天气从 2026 年起将逐步关停 ``devapi.qweather.com`` / ``api.qweather.com`` /
  ``geoapi.qweather.com`` 等公共域名，迁移到每个开发者独立的 API Host。
  当前实现允许通过环境变量覆盖 ``QWEATHER_HOST`` 与 ``QWEATHER_GEO_HOST``，
  方便在公共域名失效后切换。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


# ---- 默认域名 ---------------------------------------------------------------
# 免费订阅版默认走 devapi（天气接口）与 geoapi（城市搜索）。
DEFAULT_WEATHER_HOST = "devapi.qweather.com"
DEFAULT_GEO_HOST = "geoapi.qweather.com"

# 单次请求超时（秒）。如果超时 LLM 应该自己决定如何提示用户。
HTTP_TIMEOUT = 10.0


def _resolve_api_key(override: Optional[str] = None) -> str:
    """优先级：函数入参 > 环境变量 ``QWEATHER_KEY`` > 空串。"""
    if override and override.strip():
        return override.strip()
    return (os.getenv("QWEATHER_KEY") or "").strip()


def _resolve_hosts(weather_host: Optional[str] = None, geo_host: Optional[str] = None) -> Tuple[str, str]:
    """支持通过参数或环境变量覆盖默认域名。"""
    w = (weather_host or os.getenv("QWEATHER_HOST") or DEFAULT_WEATHER_HOST).strip()
    g = (geo_host or os.getenv("QWEATHER_GEO_HOST") or DEFAULT_GEO_HOST).strip()
    # 兼容用户把完整 URL 粘进来的情况
    w = w.replace("https://", "").replace("http://", "").rstrip("/")
    g = g.replace("https://", "").replace("http://", "").rstrip("/")
    return w, g


def _is_coordinate(location: str) -> bool:
    """判断 location 是否为 ``经度,纬度`` 形式。"""
    parts = location.split(",")
    if len(parts) != 2:
        return False
    try:
        float(parts[0].strip())
        float(parts[1].strip())
        return True
    except ValueError:
        return False


class QWeatherError(Exception):
    """仅在客户端内部使用的异常占位，向外暴露时统一转成 dict。"""


class QWeatherClient:
    """轻量异步客户端。每次实例化即可，无需复用。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        weather_host: Optional[str] = None,
        geo_host: Optional[str] = None,
        timeout: float = HTTP_TIMEOUT,
    ) -> None:
        self.api_key = _resolve_api_key(api_key)
        self.weather_host, self.geo_host = _resolve_hosts(weather_host, geo_host)
        self.timeout = timeout

    # ------------------------------------------------------------------ HTTP
    async def _get(self, host: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """统一发起 GET 请求并返回 JSON。错误用结构化 dict 返回。"""
        if not self.api_key:
            return {"error": "未配置 QWEATHER_KEY，无法访问和风天气 API"}

        url = f"https://{host}{path}"
        # 和风官方推荐 ``X-QW-Api-Key`` 请求头。query param ``key=`` 在旧凭据上仍兼容，
        # 这里两种都带上以提高兼容性。
        headers = {
            "X-QW-Api-Key": self.api_key,
            "Accept-Encoding": "gzip",
        }
        query = {**params, "key": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=query, headers=headers)
        except httpx.TimeoutException:
            logger.warning("QWeather request timeout: %s", url)
            return {"error": "天气服务超时，请稍后重试"}
        except httpx.HTTPError as exc:
            logger.warning("QWeather request failed: %s | %s", url, exc)
            return {"error": f"天气服务网络异常：{exc.__class__.__name__}"}

        # 和风对无效 KEY 实际返回 HTTP 404（不是 401），所以这里一并处理。
        if response.status_code in (401, 403, 404):
            logger.warning("QWeather auth/not-found: %s -> %s", url, response.status_code)
            return {"error": "天气服务鉴权失败或资源不存在，请检查 QWEATHER_KEY 是否正确"}
        if response.status_code >= 400:
            logger.warning("QWeather HTTP %s: %s -> %s", response.status_code, url, response.text[:200])
            return {"error": f"天气服务返回 HTTP {response.status_code}"}

        try:
            data = response.json()
        except ValueError:
            return {"error": "天气服务返回非 JSON 数据"}

        # 和风天气 v7 系列接口返回顶层 ``code`` 字段，``"200"`` 才算成功。
        # 新版预警接口 (``/weatheralert/v1/...``) 没有 ``code`` 字段，调用方需自行判断。
        code = data.get("code")
        if code is not None and code != "200":
            logger.warning("QWeather business error: %s -> code=%s", url, code)
            return {"error": f"天气服务异常: {code}"}
        return data

    # --------------------------------------------------------------- 城市搜索
    async def city_lookup(self, location: str, adm: Optional[str] = None) -> Dict[str, Any]:
        """城市搜索。``location`` 可以是城市名、LocationID 或 ``lon,lat``。

        返回结构化 dict：
        - 成功：``{"results": [...]}``，每条包含 id / name / lat / lon / adm1 / adm2 / country
        - 失败：``{"error": "..."}``
        """
        params: Dict[str, Any] = {"location": location, "lang": "zh"}
        if adm:
            params["adm"] = adm
        data = await self._get(self.geo_host, "/geo/v2/city/lookup", params)
        if "error" in data:
            return data
        locations = data.get("location") or []
        return {"results": locations}

    # ------------------------------------------------------------- 实时天气
    async def weather_now(self, location: str) -> Dict[str, Any]:
        """实时天气。``location`` 必须是 LocationID 或 ``lon,lat``。"""
        return await self._get(self.weather_host, "/v7/weather/now", {"location": location, "lang": "zh"})

    # ------------------------------------------------------------- 逐日预报
    async def weather_daily(self, location: str, days: str = "7d") -> Dict[str, Any]:
        """逐日天气预报。免费订阅版通常只开放 3d/7d。"""
        days = days if days in {"3d", "7d", "10d", "15d", "30d"} else "7d"
        return await self._get(self.weather_host, f"/v7/weather/{days}", {"location": location, "lang": "zh"})

    # ----------------------------------------------------------- 逐小时预报
    async def weather_hourly(self, location: str, hours: str = "24h") -> Dict[str, Any]:
        """逐小时天气预报。免费订阅版通常只开放 24h。"""
        hours = hours if hours in {"24h", "72h", "168h"} else "24h"
        return await self._get(self.weather_host, f"/v7/weather/{hours}", {"location": location, "lang": "zh"})

    # ------------------------------------------------------------- 生活指数
    async def indices(self, location: str, days: str = "1d", types: str = "1,3,5,9,14,16") -> Dict[str, Any]:
        """天气生活指数。``types`` 默认覆盖：运动 / 穿衣 / 紫外线 / 空气污染扩散 / 晾晒 / 交通。

        生活指数类型 ID（中国地区）见和风官方文档，常用：
        1=运动 2=洗车 3=穿衣 4=感冒 5=紫外线 6=旅游 7=花粉过敏 8=舒适度
        9=空气污染扩散 10=空调 11=太阳镜 12=化妆 13=晾晒 14=交通 15=钓鱼 16=防晒
        """
        days = days if days in {"1d", "3d"} else "1d"
        return await self._get(
            self.weather_host,
            f"/v7/indices/{days}",
            {"location": location, "type": types, "lang": "zh"},
        )

    # ---------------------------------------------------------------- 预警
    async def warning(self, lat: float, lon: float) -> Dict[str, Any]:
        """实时天气预警。新版接口位于独立路径 ``/weatheralert/v1/current/{lat}/{lon}``。

        免费订阅版的公共域名 ``devapi.qweather.com`` 不一定开放此接口，
        如果返回 404 / 业务错误，调用方应当忽略并继续提供基础天气信息。
        """
        # 经纬度限制最多两位小数
        path = f"/weatheralert/v1/current/{round(lat, 2)}/{round(lon, 2)}"
        data = await self._get(self.weather_host, path, {"lang": "zh"})
        if "error" in data:
            return data
        return {"alerts": data.get("alerts") or []}
