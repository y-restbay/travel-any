from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.chat import ChatMessage  # noqa: E402
from app.services.session_context_service import build_session_context  # noqa: E402


def _user(content: str) -> ChatMessage:
    return ChatMessage(role="user", content=content)


def test_session_context_accumulates_trip_facts():
    messages = [
        _user("第一次去冰岛，预算中等，想看自然风景"),
        _user("3个人"),
        _user("我们计划玩7天，准备自驾"),
        _user("想住带厨房的公寓，不想太赶"),
    ]

    context = build_session_context(messages)

    assert context.destination == "冰岛"
    assert context.budget == "中等"
    assert context.travelers == "3人"
    assert context.trip_length == "7天"
    assert context.transport_mode == "自驾"
    assert "自然风景" in context.interests
    assert "带厨房" in context.accommodation_preferences
    assert context.pace in {"慢节奏", "轻松"}
    assert "还不知道出行时间" in context.unresolved


def test_session_context_uses_latest_value_when_user_updates():
    messages = [
        _user("想去苏州玩两天"),
        _user("改成三天吧"),
        _user("其实还是4个人同行"),
        _user("不自驾，坐高铁过去"),
    ]

    context = build_session_context(messages)

    assert context.destination == "苏州"
    assert context.trip_length == "3天"
    assert context.travelers == "4人"
    assert context.transport_mode == "非自驾"
    assert context.latest_user_message == "不自驾，坐高铁过去"


def test_session_prompt_block_mentions_confirmed_and_unresolved():
    messages = [
        _user("我想这周末去黄山，2个人，预算有限"),
        _user("主要想徒步和看日出"),
    ]

    context = build_session_context(messages)
    block = context.prompt_block()

    assert "## Current Session Memory" in block
    assert "目的地: 黄山" in block
    assert "人数: 2人" in block
    assert "预算: 有限" in block
    assert "兴趣偏好: 徒步" in block or "兴趣偏好: 徒步、" in block
    assert "仍待确认的信息" in block
