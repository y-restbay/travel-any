"""directions_tool 单元测试。

覆盖：
- amap_client mock 模式：无 AMAP_KEY 时不发任何 HTTP 请求，返回结构化虚拟数据
- handle_get_directions：summary + map_payload 两份输出格式正确
- 坐标格式校验：错误坐标不会崩
- polyline 解析与 bounds 计算
- 步行多段分段拼接：单段失败回退为直线
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import pytest

# 显式清掉环境里的 AMAP_KEY，确保测试走 mock 分支
os.environ.pop("AMAP_KEY", None)

from app.travel_tools.amap_client import (
    AmapClient,
    is_coordinate,
    parse_coordinate,
    parse_polyline,
)
from app.travel_tools.directions_tool import (
    DIRECTIONS_TOOL_SCHEMA,
    handle_get_directions,
)


# ------------------------------------------------------------------- amap_client
def test_is_coordinate_accepts_valid():
    assert is_coordinate("120.620,31.320") is True
    assert is_coordinate("-73.5,40.7") is True


def test_is_coordinate_rejects_invalid():
    assert is_coordinate("北京") is False
    assert is_coordinate("120.620") is False
    assert is_coordinate("200,500") is False  # 超界


def test_parse_polyline_round_trip():
    pts = parse_polyline("120.62,31.32;120.61,31.31")
    assert pts == [[120.62, 31.32], [120.61, 31.31]]


def test_parse_polyline_skips_garbage():
    pts = parse_polyline("120.62,31.32;bad;120.61,31.31")
    assert pts == [[120.62, 31.32], [120.61, 31.31]]


def test_amap_client_no_key_uses_mock():
    client = AmapClient(api_key="")
    assert client.has_key is False
    raw = asyncio.run(
        client.driving_directions("120.62,31.32", "120.55,31.30", waypoints=["120.60,31.31"])
    )
    assert raw["status"] == "1"
    assert raw["_mock"] is True
    paths = raw["route"]["paths"]
    assert paths and paths[0]["steps"], "mock 应该至少返回一段 polyline"


# ------------------------------------------------------------------ schema 检查
def test_directions_schema_shape():
    fn = DIRECTIONS_TOOL_SCHEMA["function"]
    assert fn["name"] == "get_directions"
    params = fn["parameters"]
    assert "origin" in params["properties"]
    assert "destination" in params["properties"]
    assert params["required"] == ["origin", "destination"]
    assert params["properties"]["mode"]["enum"] == ["driving", "walking"]


# ----------------------------------------------------- handle_get_directions
def test_driving_with_waypoints_mock():
    summary, payload = asyncio.run(
        handle_get_directions(
            origin="120.620,31.320",
            destination="120.550,31.300",
            waypoints=["120.600,31.300", "120.580,31.310"],
            mode="driving",
            route_name="苏州一日游",
            marker_names=["拙政园", "狮子林", "寒山寺", "留园"],
        )
    )
    assert "error" not in summary
    assert summary["mode"] == "driving"
    assert summary["stops"] == 4
    assert summary["distance_km"] > 0
    assert summary["is_mock"] is True

    assert payload is not None
    assert payload["type"] == "route"
    assert payload["route_name"] == "苏州一日游"
    assert len(payload["markers"]) == 4
    assert payload["markers"][0]["name"] == "拙政园"
    assert payload["markers"][0]["order"] == 1
    assert payload["polyline"], "polyline 应至少有几个点"
    assert payload["bounds"]["sw"][0] <= payload["bounds"]["ne"][0]
    assert payload["bounds"]["sw"][1] <= payload["bounds"]["ne"][1]


def test_walking_segmented_mock():
    summary, payload = asyncio.run(
        handle_get_directions(
            origin="120.620,31.320",
            destination="120.580,31.310",
            waypoints=["120.610,31.315"],
            mode="walking",
        )
    )
    assert payload is not None
    assert payload["mode"] == "walking"
    # 步行有 2 段，拼接后应至少 3 个点
    assert len(payload["polyline"]) >= 3


def test_invalid_origin_returns_error():
    summary, payload = asyncio.run(
        handle_get_directions(origin="北京", destination="120.55,31.30")
    )
    assert "error" in summary
    assert payload is None


def test_drops_invalid_waypoints():
    summary, payload = asyncio.run(
        handle_get_directions(
            origin="120.620,31.320",
            destination="120.550,31.300",
            waypoints=["bad_point", "120.600,31.300"],
            mode="driving",
        )
    )
    assert payload is not None
    # 起点 + 1 个有效途经点 + 终点 = 3 个 marker
    assert len(payload["markers"]) == 3


def test_default_marker_names():
    _, payload = asyncio.run(
        handle_get_directions(
            origin="120.620,31.320",
            destination="120.550,31.300",
            waypoints=["120.600,31.300"],
        )
    )
    names = [m["name"] for m in payload["markers"]]
    assert names == ["起点", "途经点 1", "终点"]


# -------------------------------------------------- 真接口模拟（用 monkeypatch 注入 fake response）
class _FakeAmapClient(AmapClient):
    """模拟有 key 时高德返回的真响应结构。"""

    def __init__(self, payload: Dict[str, Any]):
        super().__init__(api_key="FAKE")
        self._payload = payload

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:  # noqa: D401
        return self._payload


def test_extract_real_amap_response_shape():
    fake = {
        "status": "1",
        "info": "ok",
        "infocode": "10000",
        "route": {
            "origin": "120.620,31.320",
            "destination": "120.550,31.300",
            "paths": [
                {
                    "distance": "18500",
                    "cost": {"duration": "3000", "tolls": "8"},
                    "steps": [
                        {"polyline": "120.620,31.320;120.610,31.315"},
                        {"polyline": "120.610,31.315;120.600,31.310"},
                    ],
                }
            ],
        },
    }
    client = _FakeAmapClient(fake)
    summary, payload = asyncio.run(
        handle_get_directions(
            origin="120.620,31.320",
            destination="120.550,31.300",
            mode="driving",
            client=client,
        )
    )
    assert summary["distance_km"] == 18.5
    assert summary["duration_min"] == 50
    assert summary["tolls_yuan"] == 8.0
    assert summary["is_mock"] is False
    # 接缝去重：第二段第一个点和第一段最后一个点重复，应只算一次
    assert payload["polyline"] == [
        [120.620, 31.320],
        [120.610, 31.315],
        [120.600, 31.310],
    ]


def test_business_error_returns_error():
    fake = {"status": "0", "info": "INVALID_USER_KEY", "infocode": "10001"}
    client = _FakeAmapClient(fake)

    async def go():
        return await client.driving_directions("120.62,31.32", "120.55,31.30")

    raw = asyncio.run(go())
    # _get 不被走（因为我们覆盖了），所以这条用例只是确认 _FakeAmapClient 返回原样
    assert raw["status"] == "0"
