from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, List, Optional

from app.schemas.chat import ChatMessage


DESTINATION_ALIASES = {
    "冰岛": "冰岛",
    "京都": "京都",
    "东京": "东京",
    "大阪": "大阪",
    "上海": "上海",
    "杭州": "杭州",
    "苏州": "苏州",
    "黄山": "黄山",
    "三亚": "三亚",
    "海岛": "海岛目的地",
}

INTEREST_KEYWORDS = {
    "自然风景": "自然风景",
    "自然": "自然风景",
    "风景": "自然风景",
    "极光": "极光",
    "温泉": "温泉",
    "徒步": "徒步",
    "摄影": "摄影",
    "拍照": "摄影",
    "美食": "美食",
    "吃": "美食",
    "人文": "人文",
    "博物馆": "博物馆",
    "历史": "历史文化",
    "亲子": "亲子体验",
    "海边": "海边",
    "海岛": "海岛",
    "购物": "购物",
    "演出": "演出活动",
    "音乐节": "演出活动",
}

ACCOMMODATION_KEYWORDS = {
    "民宿": "民宿",
    "公寓": "公寓",
    "酒店": "酒店",
    "温泉酒店": "温泉酒店",
    "带厨房": "带厨房",
    "市中心": "住市中心",
    "海景": "海景房",
}

TOPIC_KEYWORDS = {
    "天气": "weather",
    "下雨": "weather",
    "酒店": "hotel",
    "住宿": "hotel",
    "民宿": "hotel",
    "路线": "route",
    "怎么走": "route",
    "交通": "route",
    "门票": "tickets",
    "预算": "budget",
    "多少钱": "budget",
    "吃": "food",
    "餐厅": "food",
    "美食": "food",
    "景点": "attraction",
    "推荐": "planning",
    "规划": "planning",
    "行程": "planning",
    "最近": "realtime",
    "目前": "realtime",
    "现在": "realtime",
    "今年": "realtime",
    "开放": "realtime",
    "取消": "realtime",
}

DATE_PATTERNS = [
    re.compile(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}(?:\s*(?:到|至|-)\s*\d{4}[/-]\d{1,2}[/-]\d{1,2})?"),
    re.compile(r"\d{1,2}月\d{1,2}日(?:\s*(?:到|至|-)\s*\d{1,2}月\d{1,2}日)?"),
    re.compile(r"\d{1,2}月"),
]

DATE_KEYWORDS = ["周末", "这周末", "下周", "下个月", "五一", "端午", "暑假", "寒假", "国庆", "春节"]
PACE_KEYWORDS = [
    ("特种兵", "紧凑"),
    ("紧凑", "紧凑"),
    ("深度", "深度探索"),
    ("慢", "慢节奏"),
    ("不想太赶", "轻松"),
    ("不要太赶", "轻松"),
    ("太赶", "轻松"),
    ("轻松", "轻松"),
    ("休闲", "轻松"),
]

CN_NUMBERS = {
    "一": "1",
    "二": "2",
    "两": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}


@dataclass
class SessionContext:
    destination: Optional[str] = None
    departure_city: Optional[str] = None
    travelers: Optional[str] = None
    traveler_profiles: List[str] = field(default_factory=list)
    trip_length: Optional[str] = None
    date_info: Optional[str] = None
    budget: Optional[str] = None
    pace: Optional[str] = None
    transport_mode: Optional[str] = None
    interests: List[str] = field(default_factory=list)
    avoidances: List[str] = field(default_factory=list)
    accommodation_preferences: List[str] = field(default_factory=list)
    must_do: List[str] = field(default_factory=list)
    requested_topics: List[str] = field(default_factory=list)
    recent_user_requests: List[str] = field(default_factory=list)
    updates: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    latest_user_message: str = ""
    planning_active: bool = False

    def prompt_block(self) -> str:
        confirmed = []
        for label, value in [
            ("目的地", self.destination),
            ("出发地", self.departure_city),
            ("人数", self.travelers),
            ("同行画像", "、".join(self.traveler_profiles) if self.traveler_profiles else None),
            ("行程时长", self.trip_length),
            ("出行时间", self.date_info),
            ("预算", self.budget),
            ("旅行节奏", self.pace),
            ("交通方式", self.transport_mode),
            ("兴趣偏好", "、".join(self.interests) if self.interests else None),
            ("住宿偏好", "、".join(self.accommodation_preferences) if self.accommodation_preferences else None),
            ("避开事项", "、".join(self.avoidances) if self.avoidances else None),
            ("必须满足", "、".join(self.must_do) if self.must_do else None),
        ]:
            if value:
                confirmed.append(f"- {label}: {value}")

        recent = [f"- {item}" for item in self.recent_user_requests[-4:]]
        updates = [f"- {item}" for item in self.updates[-6:]]
        unresolved = [f"- {item}" for item in self.unresolved[:5]]

        sections = [
            "## Current Session Memory",
            "以下信息只来自用户在本次会话中明确说过的话。若新旧信息冲突，以最新的用户表达为准；未知信息必须保持未知，不能自行补全。",
        ]
        if self.latest_user_message:
            sections.append(f"最新用户输入: {self.latest_user_message}")
        if confirmed:
            sections.append("已确认事实:\n" + "\n".join(confirmed))
        if recent:
            sections.append("本次会话已提到的关键诉求:\n" + "\n".join(recent))
        if updates:
            sections.append("最近的重要更新:\n" + "\n".join(updates))
        if unresolved:
            sections.append("仍待确认的信息:\n" + "\n".join(unresolved))
        sections.append(
            "回答要求:\n"
            "- 用户只补充一个槽位时，必须与已确认事实合并理解，不要把它当成全新需求。\n"
            "- 不要重复询问已经确认过的信息。\n"
            "- 对未被用户明确说明的事实，不要编造；需要时只追问最关键缺口。"
        )
        return "\n\n".join(sections)

    def meta(self) -> dict:
        payload = asdict(self)
        payload["summary"] = {
            "destination": self.destination,
            "travelers": self.travelers,
            "budget": self.budget,
            "trip_length": self.trip_length,
            "transport_mode": self.transport_mode,
            "interests": self.interests,
            "unresolved": self.unresolved[:5],
        }
        return payload


def build_session_context(messages: list[ChatMessage]) -> SessionContext:
    context = SessionContext()
    user_messages = [message.content.strip() for message in messages if message.role == "user" and message.content.strip()]

    for text in user_messages:
        context.latest_user_message = text
        context.planning_active = context.planning_active or _looks_like_planning_request(text)
        _append_unique(context.recent_user_requests, _summarize_request(text), limit=8)
        _merge_topics(context, text)
        _apply_destination(context, text)
        _apply_departure_city(context, text)
        _apply_travelers(context, text)
        _apply_trip_length(context, text)
        _apply_date_info(context, text)
        _apply_budget(context, text)
        _apply_pace(context, text)
        _apply_transport(context, text)
        _apply_interests(context, text)
        _apply_accommodation(context, text)
        _apply_avoidances(context, text)
        _apply_must_do(context, text)

    context.unresolved = _infer_unresolved(context)
    return context


def _apply_destination(context: SessionContext, text: str) -> None:
    destination = _extract_destination(text)
    if destination and destination != context.destination:
        context.destination = destination
        context.updates.append(f"目的地更新为{destination}")


def _apply_departure_city(context: SessionContext, text: str) -> None:
    match = re.search(r"(?:从|由)([A-Za-z一-龥·]{2,20})出发", text)
    if not match:
        match = re.search(r"([A-Za-z一-龥·]{2,20})出发", text)
    if match:
        city = match.group(1).strip()
        if city and city != context.departure_city:
            context.departure_city = city
            context.updates.append(f"出发地更新为{city}")


def _apply_travelers(context: SessionContext, text: str) -> None:
    people_match = re.search(r"(\d+(?:-\d+)?)\s*(个人|人|位)", text)
    if people_match:
        travelers = f"{people_match.group(1)}人"
        if travelers != context.travelers:
            context.travelers = travelers
            context.updates.append(f"人数更新为{travelers}")
    elif "情侣" in text and context.travelers != "2人":
        context.travelers = "2人"
        context.updates.append("人数更新为2人")
    elif re.search(r"(一个人|独自|solo)", text) and context.travelers != "1人":
        context.travelers = "1人"
        context.updates.append("人数更新为1人")

    for keyword, label in [
        ("情侣", "情侣"),
        ("夫妻", "夫妻"),
        ("亲子", "亲子"),
        ("带父母", "带父母"),
        ("家庭", "家庭"),
        ("朋友", "朋友同行"),
    ]:
        if keyword in text and label not in context.traveler_profiles:
            context.traveler_profiles.append(label)


def _apply_trip_length(context: SessionContext, text: str) -> None:
    match = re.search(r"(\d+(?:-\d+)?)\s*(天|日|晚)", text)
    if not match:
        match = re.search(r"([一二两三四五六七八九十])\s*(天|日|晚)", text)
    if match:
        number = CN_NUMBERS.get(match.group(1), match.group(1))
        trip_length = f"{number}{match.group(2)}"
        if trip_length != context.trip_length:
            context.trip_length = trip_length
            context.updates.append(f"行程时长更新为{trip_length}")


def _apply_date_info(context: SessionContext, text: str) -> None:
    date_value = _extract_date_info(text)
    if date_value and date_value != context.date_info:
        context.date_info = date_value
        context.updates.append(f"出行时间更新为{date_value}")


def _apply_budget(context: SessionContext, text: str) -> None:
    budget = None
    if "预算中等" in text or "中等预算" in text:
        budget = "中等"
    elif "预算有限" in text or "预算不高" in text or "穷游" in text:
        budget = "有限"
    elif "预算充足" in text or "高预算" in text or "奢华" in text:
        budget = "高"
    else:
        match = re.search(r"(?:预算|人均|总预算)\s*(?:大概|约|在)?\s*([0-9]+(?:\.[0-9]+)?\s*(?:万|千|元|w|W|k|K)?)", text)
        if match:
            budget = match.group(1).replace(" ", "")
    if budget and budget != context.budget:
        context.budget = budget
        context.updates.append(f"预算更新为{budget}")


def _apply_pace(context: SessionContext, text: str) -> None:
    for keyword, label in PACE_KEYWORDS:
        if keyword in text and label != context.pace:
            context.pace = label
            context.updates.append(f"旅行节奏偏好更新为{label}")


def _apply_transport(context: SessionContext, text: str) -> None:
    transport = None
    if "不自驾" in text or "不会开车" in text or "不想开车" in text:
        transport = "非自驾"
    elif "自驾" in text or "租车" in text:
        transport = "自驾"
    elif "公共交通" in text or "地铁" in text or "火车" in text:
        transport = "公共交通"
    elif "包车" in text:
        transport = "包车"
    if transport and transport != context.transport_mode:
        context.transport_mode = transport
        context.updates.append(f"交通方式偏好更新为{transport}")


def _apply_interests(context: SessionContext, text: str) -> None:
    for keyword, label in INTEREST_KEYWORDS.items():
        if keyword in text and label not in context.interests:
            context.interests.append(label)


def _apply_accommodation(context: SessionContext, text: str) -> None:
    for keyword, label in ACCOMMODATION_KEYWORDS.items():
        if keyword in text and label not in context.accommodation_preferences:
            context.accommodation_preferences.append(label)


def _apply_avoidances(context: SessionContext, text: str) -> None:
    for pattern in [
        r"(?:不想|不要|避免|别|不去)([^，。；\n]{1,18})",
        r"(?:怕)([^，。；\n]{1,12})",
    ]:
        for match in re.finditer(pattern, text):
            phrase = match.group(1).strip(" 的")
            if phrase:
                _append_unique(context.avoidances, phrase, limit=6)


def _apply_must_do(context: SessionContext, text: str) -> None:
    for pattern in [
        r"(?:想看|想去|一定要|必须去|必须看)([^，。；\n]{1,18})",
    ]:
        for match in re.finditer(pattern, text):
            phrase = match.group(1).strip(" 的")
            if phrase:
                _append_unique(context.must_do, phrase, limit=6)


def _merge_topics(context: SessionContext, text: str) -> None:
    for keyword, topic in TOPIC_KEYWORDS.items():
        if keyword in text and topic not in context.requested_topics:
            context.requested_topics.append(topic)


def _extract_destination(text: str) -> Optional[str]:
    for keyword, label in DESTINATION_ALIASES.items():
        if keyword in text:
            return label

    for pattern in [
        r"(?:第一次去|想去|计划去|准备去|去|到)([A-Za-z一-龥·]{2,20})(?:旅游|旅行|玩|度假)?",
        r"(?:目的地|想玩|考虑去)[:：]?([A-Za-z一-龥·]{2,20})",
    ]:
        match = re.search(pattern, text)
        if not match:
            continue
        candidate = match.group(1).strip()
        if candidate and candidate not in {"旅行", "旅游", "那里", "这里", "一下", "看看"}:
            return candidate
    return None


def _extract_date_info(text: str) -> Optional[str]:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    for keyword in DATE_KEYWORDS:
        if keyword in text:
            return keyword
    return None


def _infer_unresolved(context: SessionContext) -> List[str]:
    unresolved: List[str] = []
    if context.destination and not context.trip_length:
        unresolved.append("还不知道旅行天数")
    if context.destination and not context.date_info:
        unresolved.append("还不知道出行时间")
    if context.destination and not context.transport_mode:
        unresolved.append("还不知道是否自驾或偏好的交通方式")
    if context.planning_active and not context.budget:
        unresolved.append("还不知道预算范围")
    if context.planning_active and not context.travelers:
        unresolved.append("还不知道出行人数")
    return unresolved


def _looks_like_planning_request(text: str) -> bool:
    return any(keyword in text for keyword in ["推荐", "规划", "行程", "怎么玩", "第一次去", "安排", "路线"])


def _summarize_request(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= 36:
        return compact
    return compact[:36].rstrip() + "..."


def _append_unique(items: List[str], value: Optional[str], *, limit: int) -> None:
    if not value or value in items:
        return
    items.append(value)
    if len(items) > limit:
        del items[0 : len(items) - limit]
