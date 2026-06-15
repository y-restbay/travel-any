"""identify_landmark 工具单元测试。

聚焦"防幻觉护栏"：低置信、人物图、无法解析等不可信场景必须降级为
uncertain/failed,绝不返回 success 让上层 LLM 自信回答。

不调真实 VLM,通过依赖注入塞入 _FakeVLM,避免花费 API 额度。
"""
from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from app.services.image_store import get_image_store
from app.travel_tools import landmark_tool
from app.travel_tools.landmark_tool import (
    LANDMARK_RECOGNITION_PROMPT,
    LANDMARK_TOOL_SCHEMA,
    handle_identify_landmark,
)
from app.travel_tools.vlm_client import VLMClient


class _FakeVLM(VLMClient):
    def __init__(self, *, response: str = "", raises: Optional[Exception] = None):
        super().__init__(api_key="test-key")
        self._response = response
        self._raises = raises
        self.calls = 0

    def is_ready(self) -> bool:
        return True

    async def recognize(self, image_bytes, prompt, mime="image/jpeg"):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._response


def _bypass_compress(monkeypatch):
    monkeypatch.setattr(landmark_tool, "compress_image", lambda data: data)


def _put_image() -> str:
    return get_image_store().put(b"fake-image-bytes", mime="image/jpeg")


def _run(coro):
    return asyncio.run(coro)


# ---- 防幻觉护栏:不自信场景必须降级 -----------------------------------------

def test_high_confidence_landmark_returns_success(monkeypatch):
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(
        response=(
            '{"landmark_name":"故宫","city":"北京","confidence":"高",'
            '"features":"红墙黄瓦、太和殿","reasoning":"标志性建筑明显",'
            '"is_person_focused":false}'
        )
    )
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "success"
    assert result["景点名称"] == "故宫"
    assert result["所在城市"] == "北京"
    assert result["置信度"] == "高"


def test_low_confidence_downgrades_to_uncertain(monkeypatch):
    """VLM 即使给了 landmark_name,但 confidence=低 必须降级,不能自信回答。"""
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(
        response=(
            '{"landmark_name":"某无名寺庙","city":"杭州","confidence":"低",'
            '"features":"飞檐翘角","reasoning":"特征不足以唯一定位",'
            '"is_person_focused":false}'
        )
    )
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "uncertain"
    assert "不要编造" in result["建议"]
    # 关键:即使 VLM 报了名字,工具结果里也不能直接给"景点名称"字段
    assert "景点名称" not in result


def test_missing_city_downgrades_to_uncertain(monkeypatch):
    """VLM 给了"中"置信和景点名但 city 为空,代码必须兜底降级。"""
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(
        response=(
            '{"landmark_name":"某博物馆","city":"","confidence":"中",'
            '"features":"现代玻璃幕墙","reasoning":"不熟悉具体城市",'
            '"is_person_focused":false}'
        )
    )
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "uncertain"
    assert "景点名称" not in result


def test_empty_landmark_name_returns_uncertain(monkeypatch):
    """VLM 主动说不知道(landmark_name 空),工具必须返回 uncertain。"""
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(
        response=(
            '{"landmark_name":"","city":"","confidence":"低",'
            '"features":"江南古典园林风格","reasoning":"特征不够具体",'
            '"is_person_focused":false}'
        )
    )
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "uncertain"
    assert "江南古典园林" in result["图片特征"]


def test_person_focused_image_is_rejected(monkeypatch):
    """人像图不应识别人脸,直接返回 uncertain。"""
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(
        response=(
            '{"landmark_name":"","city":"","confidence":"低",'
            '"features":"图中是一位站立的人物","reasoning":"主要是人物",'
            '"is_person_focused":true}'
        )
    )
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "uncertain"
    assert "人物" in result["提示"]


def test_unparseable_vlm_output_returns_failed(monkeypatch):
    """VLM 没按要求输出 JSON,工具不能瞎猜,必须明确 failed。"""
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(response="这张图我看不太清楚,可能是某座山。")
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "failed"
    assert "JSON" in result["错误"]
    assert "原始输出" in result


# ---- VLM 输出解析的稳健性 -------------------------------------------------

def test_json_wrapped_in_markdown_block(monkeypatch):
    """VLM 习惯性用 ```json``` 包裹时仍能解析。"""
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(
        response=(
            "```json\n"
            '{"landmark_name":"颐和园","city":"北京","confidence":"高",'
            '"features":"昆明湖、长廊","reasoning":"皇家园林标志",'
            '"is_person_focused":false}\n'
            "```"
        )
    )
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "success"
    assert result["景点名称"] == "颐和园"


def test_json_with_surrounding_text(monkeypatch):
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(
        response=(
            "分析结果如下: "
            '{"landmark_name":"长城","city":"北京","confidence":"高",'
            '"features":"砖石蜿蜒","reasoning":"特征突出",'
            '"is_person_focused":false}'
            " 以上仅供参考。"
        )
    )
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "success"
    assert result["景点名称"] == "长城"


# ---- 失败路径:每个都要稳健 -------------------------------------------------

def test_missing_image_ref_returns_failed():
    result = _run(handle_identify_landmark({}, vlm_client=_FakeVLM(response="{}")))
    assert result["状态"] == "failed"
    assert "image_ref" in result["错误"]


def test_image_not_found_or_expired_returns_failed():
    result = _run(
        handle_identify_landmark(
            {"image_ref": "img_does_not_exist"}, vlm_client=_FakeVLM(response="{}")
        )
    )
    assert result["状态"] == "failed"
    assert ("过期" in result["错误"]) or ("不存在" in result["错误"])


def test_vlm_runtime_error_returns_failed(monkeypatch):
    _bypass_compress(monkeypatch)
    ref = _put_image()
    vlm = _FakeVLM(raises=RuntimeError("network down"))
    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=vlm))
    assert result["状态"] == "failed"
    assert "RuntimeError" in result["错误"]


def test_vlm_not_configured_returns_failed(monkeypatch):
    _bypass_compress(monkeypatch)
    ref = _put_image()

    class _Unready(VLMClient):
        def __init__(self):
            super().__init__(api_key="")

        def is_ready(self) -> bool:
            return False

    result = _run(handle_identify_landmark({"image_ref": ref}, vlm_client=_Unready()))
    assert result["状态"] == "failed"
    assert "API Key" in result["错误"]


def test_compress_failure_returns_failed(monkeypatch):
    def _broken(_data):
        raise ValueError("invalid image")

    monkeypatch.setattr(landmark_tool, "compress_image", _broken)
    ref = _put_image()
    result = _run(
        handle_identify_landmark({"image_ref": ref}, vlm_client=_FakeVLM(response="{}"))
    )
    assert result["状态"] == "failed"
    assert "处理失败" in result["错误"]


# ---- prompt / schema 守护(防止有人误删关键指令) -----------------------

def test_prompt_contains_anti_hallucination_directives():
    assert "不要猜测编造" in LANDMARK_RECOGNITION_PROMPT
    assert "宁可说" in LANDMARK_RECOGNITION_PROMPT
    assert "不要识别人脸" in LANDMARK_RECOGNITION_PROMPT
    assert '"confidence"' in LANDMARK_RECOGNITION_PROMPT


def test_tool_schema_requires_image_ref():
    params = LANDMARK_TOOL_SCHEMA["function"]["parameters"]
    assert "image_ref" in params["required"]
    assert "image_ref" in params["properties"]
