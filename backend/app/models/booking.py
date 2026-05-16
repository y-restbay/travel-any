"""航班 / 酒店 / 租车 / 旅游产品 业务库存与订单表。

为多智能体 supervisor 模式提供数据底座;走 SQLite 种子数据,够 demo 用。
- Flight:航班库存;Ticket 表示一张已购票(passenger_id 默认 'demo_user_001')
- HotelInventory / CarRental / TripRecommendation:扁平的库存表,is_booked 标记是否被预订
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    flight_no: Mapped[str] = mapped_column(String(20), index=True)
    airline: Mapped[str] = mapped_column(String(80), default="")
    origin: Mapped[str] = mapped_column(String(60), index=True)
    destination: Mapped[str] = mapped_column(String(60), index=True)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price: Mapped[float] = mapped_column(Float, default=0.0)
    total_seats: Mapped[int] = mapped_column(Integer, default=180)
    available_seats: Mapped[int] = mapped_column(Integer, default=180)
    aircraft: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    flight_id: Mapped[int] = mapped_column(Integer, ForeignKey("flights.id"), index=True)
    passenger_id: Mapped[str] = mapped_column(String(40), default="demo_user_001", index=True)
    seat: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    flight: Mapped["Flight"] = relationship("Flight", lazy="joined")


class HotelInventory(Base):
    __tablename__ = "hotels_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    location: Mapped[str] = mapped_column(String(80), index=True)
    price_per_night: Mapped[float] = mapped_column(Float, default=0.0)
    price_tier: Mapped[str] = mapped_column(String(20), default="midscale")
    rating: Mapped[float] = mapped_column(Float, default=4.0)
    description: Mapped[str] = mapped_column(Text, default="")
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    booked_by: Mapped[str] = mapped_column(String(40), default="")
    checkin_date: Mapped[str] = mapped_column(String(20), default="")
    checkout_date: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CarRental(Base):
    __tablename__ = "car_rentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company: Mapped[str] = mapped_column(String(120), index=True)
    location: Mapped[str] = mapped_column(String(80), index=True)
    vehicle_class: Mapped[str] = mapped_column(String(40), default="经济型")
    daily_rate: Mapped[float] = mapped_column(Float, default=0.0)
    transmission: Mapped[str] = mapped_column(String(20), default="自动")
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    booked_by: Mapped[str] = mapped_column(String(40), default="")
    start_date: Mapped[str] = mapped_column(String(20), default="")
    end_date: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TripRecommendation(Base):
    __tablename__ = "trip_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    location: Mapped[str] = mapped_column(String(80), index=True)
    keywords: Mapped[str] = mapped_column(String(400), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    duration_hours: Mapped[float] = mapped_column(Float, default=2.0)
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    booked_by: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
