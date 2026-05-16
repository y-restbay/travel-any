"""旅游产品 / 景点门票工具:search / book / update / cancel。

与 generate_itinerary_summary 互补:itinerary 是 LLM 整合的整段行程文本,
这里是真实可下单的库存(景点门票 / 一日游产品)。
"""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import or_, select

from app.db.session import SessionLocal
from app.models.booking import TripRecommendation
from app.travel_tools.flights_booking_tool import DEMO_PASSENGER_ID, _approved


def _trip_to_dict(rec: TripRecommendation) -> dict:
    return {
        "recommendation_id": rec.id,
        "name": rec.name,
        "location": rec.location,
        "keywords": rec.keywords,
        "description": rec.description,
        "price": rec.price,
        "duration_hours": rec.duration_hours,
        "is_booked": rec.is_booked,
    }


@tool
def search_trip_recommendations(
    location: Optional[str] = None,
    name: Optional[str] = None,
    keywords: Optional[str] = None,
    limit: int = 10,
) -> str:
    """查询旅游产品 / 景点门票。

    参数:
    - location: 城市
    - name: 名称关键字(模糊匹配)
    - keywords: 兴趣关键字,如 '园林'、'亲子'(模糊匹配 keywords 列)
    """
    with SessionLocal() as db:
        stmt = select(TripRecommendation)
        if location:
            stmt = stmt.where(TripRecommendation.location == location)
        if name:
            stmt = stmt.where(TripRecommendation.name.like(f"%{name}%"))
        if keywords:
            stmt = stmt.where(
                or_(
                    TripRecommendation.keywords.like(f"%{keywords}%"),
                    TripRecommendation.description.like(f"%{keywords}%"),
                )
            )
        stmt = stmt.order_by(TripRecommendation.price).limit(max(1, min(limit, 50)))
        rows = db.scalars(stmt).all()
    return json.dumps([_trip_to_dict(r) for r in rows], ensure_ascii=False)


@tool
def book_excursion(recommendation_id: int) -> str:
    """预订一个旅游产品 / 景点门票。**敏感操作,需要用户确认**。"""
    with SessionLocal() as db:
        rec = db.get(TripRecommendation, recommendation_id)
        if not rec:
            return json.dumps({"error": f"未找到 recommendation_id={recommendation_id}"}, ensure_ascii=False)
        if rec.is_booked:
            return json.dumps({"error": "该产品已被预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "book_excursion",
                "summary": f"预订 {rec.name}(¥{rec.price})",
                "details": _trip_to_dict(rec),
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        rec.is_booked = True
        rec.booked_by = DEMO_PASSENGER_ID
        db.commit()
    return json.dumps({"状态": "success", "recommendation_id": recommendation_id}, ensure_ascii=False)


@tool
def update_excursion(recommendation_id: int, details: str) -> str:
    """更新旅游产品的备注 / 详情。**敏感操作,需要用户确认**。"""
    with SessionLocal() as db:
        rec = db.get(TripRecommendation, recommendation_id)
        if not rec or not rec.is_booked:
            return json.dumps({"error": "该产品没有进行中的预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "update_excursion",
                "summary": f"更新 {rec.name} 的备注",
                "details": {"current": _trip_to_dict(rec), "new_details": details},
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        rec.description = details
        db.commit()
    return json.dumps({"状态": "success", "recommendation_id": recommendation_id}, ensure_ascii=False)


@tool
def cancel_excursion(recommendation_id: int) -> str:
    """取消旅游产品预订。**敏感操作,需要用户确认**。"""
    with SessionLocal() as db:
        rec = db.get(TripRecommendation, recommendation_id)
        if not rec or not rec.is_booked:
            return json.dumps({"error": "该产品没有进行中的预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "cancel_excursion",
                "summary": f"取消 {rec.name} 的预订",
                "details": _trip_to_dict(rec),
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        rec.is_booked = False
        rec.booked_by = ""
        db.commit()
    return json.dumps({"状态": "success", "recommendation_id": recommendation_id}, ensure_ascii=False)
