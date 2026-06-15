"""端到端关键节点测试:identify_landmark 工具结果 → LLM answer 阶段引导文本。

react_chat_service 通过两个函数把工具结果"翻译"给 LLM:
- _summarize_observation: 在 SSE observation 事件里给前端一句话摘要
- _tool_answer_context:    拼进 answer 阶段 system prompt 的结构化事实块

如果 identify_landmark 的 uncertain/failed 状态在这两步丢失,LLM 拿不到
"不要自信回答"的明确引导,可能编造景点名。本文件锁死这两个桥的行为。
"""
from __future__ import annotations

import json

from app.services.react_chat_service import (
    _summarize_observation,
    _tool_answer_context,
)


# ---- _summarize_observation: 前端 observation 摘要 -------------------------

def test_summarize_success_shows_landmark_name():
    raw = json.dumps(
        {"状态": "success", "景点名称": "故宫", "所在城市": "北京"},
        ensure_ascii=False,
    )
    summary = _summarize_observation("identify_landmark", raw)
    assert "故宫" in summary


def test_summarize_uncertain_flags_warning():
    raw = json.dumps({"状态": "uncertain", "图片特征": "江南古典园林"}, ensure_ascii=False)
    summary = _summarize_observation("identify_landmark", raw)
    assert "无法确定" in summary
    # 不能落入兜底的"已获取结果",那会误导前端
    assert summary != "已获取结果"


def test_summarize_failed_flags_warning():
    raw = json.dumps({"状态": "failed", "错误": "VLM 网络异常"}, ensure_ascii=False)
    summary = _summarize_observation("identify_landmark", raw)
    assert "失败" in summary
    assert summary != "已获取结果"


# ---- _tool_answer_context: 注入 answer 阶段 system prompt 的事实块 --------

def test_answer_context_success_allows_naming():
    raw = json.dumps(
        {
            "状态": "success",
            "景点名称": "颐和园",
            "所在城市": "北京",
            "置信度": "高",
        },
        ensure_ascii=False,
    )
    block = _tool_answer_context(
        "identify_landmark", {"image_ref": "img_x"}, raw, observation_detail=""
    )
    assert "颐和园" in block
    assert "可以直接称呼这个景点名" in block


def test_answer_context_uncertain_forbids_naming():
    """这是最关键的端到端断言:uncertain 必须明确告诉 LLM 不许说景点名。"""
    raw = json.dumps(
        {
            "状态": "uncertain",
            "图片特征": "江南古典园林风格",
            "推测": "特征不足以唯一定位",
            "建议": "礼貌询问用户城市",
        },
        ensure_ascii=False,
    )
    block = _tool_answer_context(
        "identify_landmark", {"image_ref": "img_x"}, raw, observation_detail=""
    )
    assert block, "uncertain 状态必须返回非空引导,不能让 LLM 没有上下文"
    assert "严禁" in block
    assert "不要写" in block
    assert "无法确定" in block or "没能识别" in block
    # 不能把"江南古典园林"这种暗示性特征拼成肯定句
    assert "可以直接称呼" not in block


def test_answer_context_failed_forbids_fabrication():
    raw = json.dumps(
        {"状态": "failed", "错误": "VLM 未配置 API Key"}, ensure_ascii=False
    )
    block = _tool_answer_context(
        "identify_landmark", {"image_ref": "img_x"}, raw, observation_detail=""
    )
    assert block
    assert "识别失败" in block
    assert "不得编造" in block or "如实说明" in block


def test_answer_context_handles_unparseable_result():
    """工具异常返回非 JSON 时,_tool_answer_context 不能崩。"""
    block = _tool_answer_context(
        "identify_landmark", {"image_ref": "img_x"}, "garbage non-json", observation_detail=""
    )
    # 当前实现对无法解析的内容返回空串,这是合理的兜底
    assert block == ""


# ---- 锁死关键护栏字符串(避免有人误改) -------------------------------------

def test_uncertain_context_mentions_prohibited_phrases():
    """uncertain 引导必须明确禁止 LLM 用"这看起来是 XX""可能是 XX"等暗示句式。"""
    raw = json.dumps({"状态": "uncertain", "图片特征": "..."}, ensure_ascii=False)
    block = _tool_answer_context("identify_landmark", {}, raw, "")
    assert "这看起来是" in block or "可能是" in block, (
        "uncertain 引导必须列出常见暗示句式作为反例,否则 LLM 会绕过禁令"
    )
