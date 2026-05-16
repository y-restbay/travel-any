"""航班预订相关工具:search / fetch_user / update_ticket / cancel_ticket。

设计要点:
- search_flights / fetch_user_flight_information 是只读工具
- update_ticket / cancel_ticket 是 sensitive,执行前调 ``interrupt()`` 让前端确认
- 数据库 session 用 SessionLocal() 自治,不依赖 FastAPI Depends
- 所有工具失败时返回结构化字符串,绝不抛异常给 LLM
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import List, Optional

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import and_, select

from app.db.session import SessionLocal
from app.models.booking import Flight, Ticket

DEMO_PASSENGER_ID = "demo_user_001"


def _flight_to_dict(flight: Flight) -> dict:
    return {
        "flight_id": flight.id,
        "flight_no": flight.flight_no,
        "airline": flight.airline,
        "origin": flight.origin,
        "destination": flight.destination,
        "departure_time": flight.departure_time.isoformat() if flight.departure_time else "",
        "arrival_time": flight.arrival_time.isoformat() if flight.arrival_time else "",
        "price": flight.price,
        "available_seats": flight.available_seats,
        "aircraft": flight.aircraft,
        "status": flight.status,
    }


@tool
def search_flights(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
) -> str:
    """查询国内航班库存。

    参数:
    - origin: 出发城市中文名,如 '上海'
    - destination: 到达城市中文名,如 '成都'
    - start_date / end_date: ISO 日期字符串 'YYYY-MM-DD',筛选出发时间范围
    - limit: 最多返回多少条,默认 10

    返回 JSON 字符串,含 flight_id / 票价 / 余座等。
    """
    with SessionLocal() as db:
        stmt = select(Flight).where(Flight.status == "scheduled")
        if origin:
            stmt = stmt.where(Flight.origin == origin)
        if destination:
            stmt = stmt.where(Flight.destination == destination)
        if start_date:
            try:
                stmt = stmt.where(Flight.departure_time >= datetime.fromisoformat(start_date))
            except ValueError:
                pass
        if end_date:
            try:
                stmt = stmt.where(Flight.departure_time <= datetime.fromisoformat(end_date) + _eod())
            except ValueError:
                pass
        stmt = stmt.order_by(Flight.departure_time).limit(max(1, min(limit, 50)))
        rows = db.scalars(stmt).all()
    return json.dumps([_flight_to_dict(f) for f in rows], ensure_ascii=False)


def _eod():
    from datetime import timedelta
    return timedelta(hours=23, minutes=59)


@tool
def fetch_user_flight_information() -> str:
    """查询当前 demo 用户已购买的所有机票及关联航班信息。

    无参数。返回 JSON 字符串,空数组表示用户还没有票。
    """
    with SessionLocal() as db:
        stmt = (
            select(Ticket)
            .where(and_(Ticket.passenger_id == DEMO_PASSENGER_ID, Ticket.status == "active"))
            .order_by(Ticket.created_at.desc())
        )
        tickets = db.scalars(stmt).all()
        result = []
        for t in tickets:
            result.append(
                {
                    "ticket_no": t.ticket_no,
                    "seat": t.seat,
                    "status": t.status,
                    "flight": _flight_to_dict(t.flight) if t.flight else None,
                }
            )
    return json.dumps(result, ensure_ascii=False)


@tool
def update_ticket_to_new_flight(ticket_no: str, new_flight_id: int) -> str:
    """把用户已有的机票改签到一个新的航班。**敏感操作,需要用户确认**。

    参数:
    - ticket_no: 现有机票号
    - new_flight_id: 目标航班的 flight_id(用 search_flights 查到)

    工具会先弹出确认面板,用户拒绝时取消改签。
    """
    with SessionLocal() as db:
        ticket = db.scalar(select(Ticket).where(Ticket.ticket_no == ticket_no))
        if not ticket:
            return json.dumps({"error": f"未找到票号 {ticket_no}"}, ensure_ascii=False)
        if ticket.passenger_id != DEMO_PASSENGER_ID:
            return json.dumps({"error": "无权操作此票号"}, ensure_ascii=False)
        new_flight = db.get(Flight, new_flight_id)
        if not new_flight:
            return json.dumps({"error": f"未找到 flight_id={new_flight_id}"}, ensure_ascii=False)
        old_flight = ticket.flight

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "update_ticket_to_new_flight",
                "summary": f"将票号 {ticket_no} 改签到 {new_flight.flight_no} ({new_flight.origin}→{new_flight.destination})",
                "details": {
                    "ticket_no": ticket_no,
                    "old": _flight_to_dict(old_flight) if old_flight else None,
                    "new": _flight_to_dict(new_flight),
                },
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled", "reason": "用户拒绝改签"}, ensure_ascii=False)

        ticket.flight_id = new_flight.id
        ticket.status = "active"
        db.commit()
    return json.dumps(
        {"状态": "success", "ticket_no": ticket_no, "new_flight_id": new_flight_id}, ensure_ascii=False
    )


@tool
def cancel_ticket(ticket_no: str) -> str:
    """取消用户的一张机票。**敏感操作,需要用户确认**。

    参数:
    - ticket_no: 要取消的票号

    工具会弹出确认面板;用户拒绝时不会取消。
    """
    with SessionLocal() as db:
        ticket = db.scalar(select(Ticket).where(Ticket.ticket_no == ticket_no))
        if not ticket:
            return json.dumps({"error": f"未找到票号 {ticket_no}"}, ensure_ascii=False)
        if ticket.passenger_id != DEMO_PASSENGER_ID:
            return json.dumps({"error": "无权操作此票号"}, ensure_ascii=False)

        decision = interrupt(
            {
                "type": "tool_approval",
                "tool_name": "cancel_ticket",
                "summary": f"取消票号 {ticket_no}({ticket.flight.flight_no if ticket.flight else ''})",
                "details": {
                    "ticket_no": ticket_no,
                    "flight": _flight_to_dict(ticket.flight) if ticket.flight else None,
                },
            }
        )
        if not _approved(decision):
            return json.dumps({"状态": "cancelled", "reason": "用户拒绝取消"}, ensure_ascii=False)

        ticket.status = "cancelled"
        db.commit()
    return json.dumps({"状态": "success", "ticket_no": ticket_no}, ensure_ascii=False)


def _approved(decision: object) -> bool:
    """统一判断 resume 值是否表示通过。

    支持 True、'yes'、'approve'、{'action': 'approve'} 这几种形态。
    """
    if decision is True:
        return True
    if isinstance(decision, str):
        return decision.lower() in {"yes", "y", "approve", "ok", "confirm"}
    if isinstance(decision, dict):
        action = str(decision.get("action", "")).lower()
        return action in {"approve", "yes", "confirm"} or decision.get("approved") is True
    return False
