"""酒店预订相关工具:search / book / update / cancel(SQLite 库存版)。

与现有 search_places/POI 解耦:这里走业务库存表 hotels_inventory。
"""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.booking import HotelInventory
from app.travel_tools.flights_booking_tool import DEMO_PASSENGER_ID, _approved


def _hotel_to_dict(hotel: HotelInventory) -> dict:
    return {
        "hotel_id": hotel.id,
        "name": hotel.name,
        "location": hotel.location,
        "price_per_night": hotel.price_per_night,
        "price_tier": hotel.price_tier,
        "rating": hotel.rating,
        "is_booked": hotel.is_booked,
        "checkin_date": hotel.checkin_date,
        "checkout_date": hotel.checkout_date,
    }


@tool
def search_hotels_inventory(
    location: Optional[str] = None,
    name: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = 10,
) -> str:
    """查询酒店库存(用于预订)。

    参数:
    - location: 城市,如 '上海'
    - name: 酒店名关键字
    - max_price: 单晚价格上限
    - limit: 最多返回多少条,默认 10
    """
    with SessionLocal() as db:
        stmt = select(HotelInventory).where(HotelInventory.is_booked.is_(False))
        if location:
            stmt = stmt.where(HotelInventory.location == location)
        if name:
            stmt = stmt.where(HotelInventory.name.like(f"%{name}%"))
        if max_price is not None:
            stmt = stmt.where(HotelInventory.price_per_night <= max_price)
        stmt = stmt.order_by(HotelInventory.price_per_night).limit(max(1, min(limit, 50)))
        rows = db.scalars(stmt).all()
    return json.dumps([_hotel_to_dict(h) for h in rows], ensure_ascii=False)


@tool
def book_hotel(hotel_id: int, checkin_date: str, checkout_date: str) -> str:
    """预订一家酒店。**敏感操作,需要用户确认**。

    参数:
    - hotel_id: 酒店 ID(用 search_hotels_inventory 查到)
    - checkin_date: 入住日期 'YYYY-MM-DD'
    - checkout_date: 退房日期 'YYYY-MM-DD'
    """
    with SessionLocal() as db:
        hotel = db.get(HotelInventory, hotel_id)
        if not hotel:
            return json.dumps({"error": f"未找到 hotel_id={hotel_id}"}, ensure_ascii=False)
        if hotel.is_booked:
            return json.dumps({"error": "该酒店已被预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "book_hotel",
                "summary": f"预订 {hotel.name}({checkin_date} → {checkout_date},¥{hotel.price_per_night}/晚)",
                "details": {**_hotel_to_dict(hotel), "checkin_date": checkin_date, "checkout_date": checkout_date},
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled", "reason": "用户拒绝预订"}, ensure_ascii=False)

        hotel.is_booked = True
        hotel.booked_by = DEMO_PASSENGER_ID
        hotel.checkin_date = checkin_date
        hotel.checkout_date = checkout_date
        hotel_name = hotel.name  # 在 session 内取值,避免 commit + with 关闭后 detached
        db.commit()
    return json.dumps({"状态": "success", "hotel_id": hotel_id, "酒店": hotel_name}, ensure_ascii=False)


@tool
def update_hotel_booking(
    hotel_id: int,
    checkin_date: Optional[str] = None,
    checkout_date: Optional[str] = None,
) -> str:
    """修改酒店预订的入住 / 退房日期。**敏感操作,需要用户确认**。"""
    with SessionLocal() as db:
        hotel = db.get(HotelInventory, hotel_id)
        if not hotel or not hotel.is_booked:
            return json.dumps({"error": "该酒店没有进行中的预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "update_hotel_booking",
                "summary": f"修改 {hotel.name} 的预订日期",
                "details": {
                    "hotel": _hotel_to_dict(hotel),
                    "new_checkin_date": checkin_date,
                    "new_checkout_date": checkout_date,
                },
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        if checkin_date:
            hotel.checkin_date = checkin_date
        if checkout_date:
            hotel.checkout_date = checkout_date
        db.commit()
    return json.dumps({"状态": "success", "hotel_id": hotel_id}, ensure_ascii=False)


@tool
def cancel_hotel(hotel_id: int) -> str:
    """取消一家酒店的预订。**敏感操作,需要用户确认**。"""
    with SessionLocal() as db:
        hotel = db.get(HotelInventory, hotel_id)
        if not hotel or not hotel.is_booked:
            return json.dumps({"error": "该酒店没有进行中的预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "cancel_hotel",
                "summary": f"取消 {hotel.name} 的预订",
                "details": _hotel_to_dict(hotel),
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        hotel.is_booked = False
        hotel.booked_by = ""
        hotel.checkin_date = ""
        hotel.checkout_date = ""
        db.commit()
    return json.dumps({"状态": "success", "hotel_id": hotel_id}, ensure_ascii=False)
