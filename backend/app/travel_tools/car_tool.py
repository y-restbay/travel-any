"""租车工具:search / book / update / cancel。"""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.booking import CarRental
from app.travel_tools.flights_booking_tool import DEMO_PASSENGER_ID, _approved


def _car_to_dict(car: CarRental) -> dict:
    return {
        "rental_id": car.id,
        "company": car.company,
        "location": car.location,
        "vehicle_class": car.vehicle_class,
        "daily_rate": car.daily_rate,
        "transmission": car.transmission,
        "is_booked": car.is_booked,
        "start_date": car.start_date,
        "end_date": car.end_date,
    }


@tool
def search_car_rentals(
    location: Optional[str] = None,
    vehicle_class: Optional[str] = None,
    max_daily_rate: Optional[float] = None,
    limit: int = 10,
) -> str:
    """查询可租用的车辆。

    参数:
    - location: 取车城市
    - vehicle_class: 车型(经济型 / 紧凑型 / 中型 / SUV / 豪华型)
    - max_daily_rate: 日租金上限
    """
    with SessionLocal() as db:
        stmt = select(CarRental).where(CarRental.is_booked.is_(False))
        if location:
            stmt = stmt.where(CarRental.location == location)
        if vehicle_class:
            stmt = stmt.where(CarRental.vehicle_class == vehicle_class)
        if max_daily_rate is not None:
            stmt = stmt.where(CarRental.daily_rate <= max_daily_rate)
        stmt = stmt.order_by(CarRental.daily_rate).limit(max(1, min(limit, 50)))
        rows = db.scalars(stmt).all()
    return json.dumps([_car_to_dict(c) for c in rows], ensure_ascii=False)


@tool
def book_car_rental(rental_id: int, start_date: str, end_date: str) -> str:
    """预订租车。**敏感操作,需要用户确认**。

    参数:
    - rental_id: 车辆 ID
    - start_date / end_date: 'YYYY-MM-DD'
    """
    with SessionLocal() as db:
        car = db.get(CarRental, rental_id)
        if not car:
            return json.dumps({"error": f"未找到 rental_id={rental_id}"}, ensure_ascii=False)
        if car.is_booked:
            return json.dumps({"error": "该车辆已被预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "book_car_rental",
                "summary": f"预订 {car.company} {car.vehicle_class}({start_date} → {end_date},¥{car.daily_rate}/天)",
                "details": {**_car_to_dict(car), "start_date": start_date, "end_date": end_date},
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        car.is_booked = True
        car.booked_by = DEMO_PASSENGER_ID
        car.start_date = start_date
        car.end_date = end_date
        db.commit()
    return json.dumps({"状态": "success", "rental_id": rental_id}, ensure_ascii=False)


@tool
def update_car_rental(
    rental_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """修改租车的日期。**敏感操作,需要用户确认**。"""
    with SessionLocal() as db:
        car = db.get(CarRental, rental_id)
        if not car or not car.is_booked:
            return json.dumps({"error": "该车辆没有进行中的预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "update_car_rental",
                "summary": f"修改 {car.company} {car.vehicle_class} 的租期",
                "details": {
                    "car": _car_to_dict(car),
                    "new_start_date": start_date,
                    "new_end_date": end_date,
                },
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        if start_date:
            car.start_date = start_date
        if end_date:
            car.end_date = end_date
        db.commit()
    return json.dumps({"状态": "success", "rental_id": rental_id}, ensure_ascii=False)


@tool
def cancel_car_rental(rental_id: int) -> str:
    """取消租车。**敏感操作,需要用户确认**。"""
    with SessionLocal() as db:
        car = db.get(CarRental, rental_id)
        if not car or not car.is_booked:
            return json.dumps({"error": "该车辆没有进行中的预订"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "cancel_car_rental",
                "summary": f"取消 {car.company} {car.vehicle_class} 的租车",
                "details": _car_to_dict(car),
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled"}, ensure_ascii=False)

        car.is_booked = False
        car.booked_by = ""
        car.start_date = ""
        car.end_date = ""
        db.commit()
    return json.dumps({"状态": "success", "rental_id": rental_id}, ensure_ascii=False)
