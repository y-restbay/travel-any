"""联网搜索上下文:开关 ON 时在 LLM 生成前强制走一遍 Tavily。

产出三样东西:
- ``sources``    : 编号后的网页来源(网页独立编号 1..N),给前端思考面板/来源卡
- ``prompt_block``: 注入 system prompt 的"可引用来源 + 引用规则"
- ``status``     : success / empty / failed,失败优雅降级(不报错、不强制编号)

刻意不 import chat_service(避免循环依赖),query 提取在本模块内做。
``handle_realtime_search`` 自带 30min 缓存,这里直接复用。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.schemas.chat import ChatMessage
from app.travel_tools.realtime_search_tool import handle_realtime_search

# 口语/规划类填充词,丢给搜索引擎纯属噪音,检索前剔除
_FILLER_RE = re.compile(
    r"帮我看看|帮我查查?|帮我搜一?下?|帮我规划一下|帮我安排一下|帮我推荐|帮我|帮忙|"
    r"麻烦你|麻烦|我想问一?下|想问一?下|我想知道|我想|我要|请问|请|"
    r"顺便|可以吗|好吗|谢谢|规划一下|安排一下|看看"
)


def _query_from_messages(messages: List[ChatMessage]) -> str:
    """启发式构造检索 query:会话目的地 + 用户问题(去口语填充、截断)。

    不做 LLM 改写(零延迟)。Tavily 偏好"地点+主题"的精简关键词,
    用户原话常是长口语句,逐字照搬会显著拉低召回质量。
    """
    user_texts = [m.content.strip() for m in messages if m.role == "user" and m.content.strip()]
    if not user_texts:
        return "最新旅行信息"
    raw_q = user_texts[-1]

    # 1. 去口语/规划填充词,合并空白;全被剔除则回退原句,绝不交空 query
    cleaned = re.sub(r"\s+", " ", _FILLER_RE.sub(" ", raw_q)).strip(" ，,。.、")
    if not cleaned:
        cleaned = raw_q

    # 2. 会话已知目的地补进 query(用户没在本句重复时)
    try:
        from app.services.session_context_service import build_session_context

        destination = (build_session_context(messages).destination or "").strip()
    except Exception:
        destination = ""
    if destination and destination not in cleaned:
        cleaned = f"{destination} {cleaned}"

    # 3. Tavily 偏好精简关键词,过长截断
    return cleaned[:80].strip()


def _build_prompt_block(sources: List[Dict[str, Any]], answer_summary: str) -> str:
    lines = [f"## 联网检索结果（可引用，共 {len(sources)} 条）"]
    if answer_summary:
        lines.append(f"检索引擎摘要：{answer_summary}")
    for s in sources:
        lines.append(f"[{s['n']}] {s['title']} — {s['url']}")
        if s.get("snippet"):
            lines.append(s["snippet"])
    lines.append(
        "\n引用规则（务必遵守）：\n"
        "- 使用上述某条网页信息时，在该句末尾紧跟编号标注，如 [1]，多条用 [1][3]\n"
        "- 只写编号，绝不要在正文写出 URL 或站点名（URL 只在思考过程展示）\n"
        "- 没用到的来源不必标注；本地知识库与常识不参与编号\n"
        "- 网页信息与常识冲突时以网页为准，并提示用户出行前再次确认"
    )
    return "\n".join(lines)


_DEGRADE_BLOCK = (
    "## 联网检索\n"
    "本轮联网检索不可用或无结果，请基于已有知识与本地资料回答，"
    "不要编造来源，也不要强制添加编号标注。"
)

# 联网搜索开关「未开启」时注入：模型无实时检索能力，遇到时效性诉求按提示词引导用户开启开关。
WEB_SEARCH_OFF_BLOCK = (
    "## 联网搜索（当前未开启）\n"
    "你当前没有实时联网检索能力（用户未开启「联网搜索」开关）。\n"
    "- 若用户问题依赖最新/实时信息（近期活动与排期、临时闭馆或限流、最新签证与交通政策、"
    "突发情况，或含「最近/现在/今年/这个月/还开吗」等时效表述）：不要编造或臆测实时内容，"
    "应明确、简短地告知用户——该问题需要实时联网信息，请点击输入框上方的「联网搜索」开关开启后重新提问。\n"
    "- 其余基于稳定常识与本地资料可正常回答，无需提醒。"
)


async def build_web_search_context(
    messages: List[ChatMessage],
    *,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """强制联网检索并构造注入上下文。绝不抛异常,失败走降级。"""
    query = _query_from_messages(messages)
    try:
        raw = await handle_realtime_search(
            {"query": query, "time_range": "week", "max_results": 5},
            api_key=api_key,
        )
    except Exception as exc:  # 兜底,绝不让异常冒泡到 SSE 流
        raw = {"状态": "failed", "错误": f"{exc.__class__.__name__}: {exc}"}

    if raw.get("状态") != "success":
        return {
            "status": "failed",
            "query": query,
            "sources": [],
            "answer_summary": "",
            "reason": raw.get("错误", "联网检索服务不可用"),
            "prompt_block": _DEGRADE_BLOCK,
        }

    results = raw.get("结果", []) or []
    sources: List[Dict[str, Any]] = [
        {
            "n": i,
            "title": (r.get("标题") or "未命名网页").strip(),
            "url": (r.get("链接") or "").strip(),
            "snippet": (r.get("摘要") or "").strip(),
            "published": (r.get("发布时间") or "未知"),
        }
        for i, r in enumerate(results, start=1)
        if (r.get("链接") or "").strip()
    ]

    if not sources:
        return {
            "status": "empty",
            "query": query,
            "sources": [],
            "answer_summary": raw.get("AI摘要", ""),
            "reason": "未检索到相关网页",
            "prompt_block": _DEGRADE_BLOCK,
        }

    answer_summary = raw.get("AI摘要", "")
    return {
        "status": "success",
        "query": query,
        "sources": sources,
        "answer_summary": answer_summary,
        "reason": "",
        "prompt_block": _build_prompt_block(sources, answer_summary),
    }
