"""为多智能体 supervisor 模式生成业务种子数据。

可重复执行:每次先清空 4 张业务表(flights / tickets / hotels_inventory /
car_rentals / trip_recommendations),再批量插入。

跑法:
    cd backend && source .venv/bin/activate && python -m scripts.seed_booking_data
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.booking import (  # noqa: F401  注册表
    CarRental,
    Flight,
    HotelInventory,
    Ticket,
    TripRecommendation,
)

CITIES = ["北京", "上海", "广州", "深圳", "成都", "杭州", "苏州", "西安", "南京", "重庆"]
AIRLINES = [
    ("CA", "中国国际航空"),
    ("MU", "中国东方航空"),
    ("CZ", "中国南方航空"),
    ("HU", "海南航空"),
    ("MF", "厦门航空"),
]
HOTEL_BRANDS = [
    ("如家精选", "economy", 320, 3.8),
    ("汉庭酒店", "economy", 280, 3.6),
    ("亚朵酒店", "midscale", 580, 4.4),
    ("全季酒店", "midscale", 480, 4.2),
    ("锦江都城", "midscale", 520, 4.1),
    ("万豪酒店", "luxury", 1380, 4.7),
    ("希尔顿酒店", "luxury", 1480, 4.7),
    ("文华东方", "luxury", 2680, 4.9),
]
CAR_COMPANIES = ["神州租车", "一嗨租车", "首汽租车", "携程租车", "悟空租车"]
CAR_CLASSES = [
    ("经济型", 199, "自动"),
    ("紧凑型", 269, "自动"),
    ("中型", 369, "自动"),
    ("SUV", 489, "自动"),
    ("豪华型", 899, "自动"),
]
ATTRACTIONS = {
    "北京": [("故宫博物院", "人文,皇家,世界遗产", 60), ("颐和园", "园林,皇家", 30), ("八达岭长城", "户外,世界遗产", 40), ("天坛公园", "人文,园林", 15), ("798艺术区", "艺术,潮流", 0), ("圆明园", "人文,园林", 25)],
    "上海": [("外滩夜景游船", "夜景,城市", 150), ("迪士尼乐园", "亲子,主题乐园", 475), ("豫园", "园林,人文", 40), ("田子坊", "潮流,文创", 0), ("上海博物馆", "人文,博物馆", 0), ("陆家嘴观光", "城市,夜景", 180)],
    "广州": [("长隆野生动物世界", "亲子,动物", 350), ("沙面历史街区", "人文,建筑", 0), ("白云山", "户外,自然", 5), ("陈家祠", "人文,建筑", 10), ("广州塔", "城市,夜景", 150), ("珠江夜游", "夜景,游船", 100)],
    "深圳": [("世界之窗", "主题乐园", 220), ("欢乐谷", "亲子,主题乐园", 230), ("莲花山公园", "城市,自然", 0), ("大梅沙海滨", "海滨,户外", 0), ("华侨城创意园", "潮流,文创", 0), ("深圳湾公园", "城市,自然", 0)],
    "成都": [("大熊猫繁育研究基地", "亲子,动物", 55), ("宽窄巷子", "人文,美食", 0), ("锦里古街", "人文,美食", 0), ("武侯祠", "人文,三国", 50), ("都江堰", "世界遗产", 80), ("青城山", "户外,道教", 90)],
    "杭州": [("西湖游船", "园林,夜景", 70), ("灵隐寺", "人文,佛教", 75), ("千岛湖", "户外,自然", 130), ("宋城千古情", "演艺,主题", 310), ("龙井村品茶", "茶文化,户外", 0), ("西溪湿地", "自然,户外", 80)],
    "苏州": [("拙政园", "园林,世界遗产", 90), ("狮子林", "园林", 40), ("寒山寺", "人文,佛教", 20), ("平江路", "人文,美食", 0), ("山塘街", "人文,夜景", 0), ("虎丘", "园林,历史", 80)],
    "西安": [("兵马俑博物馆", "世界遗产,人文", 120), ("大雁塔", "人文,佛教", 40), ("城墙骑行", "户外,人文", 54), ("回民街美食", "美食,人文", 0), ("华清宫", "人文,温泉", 120), ("陕西历史博物馆", "博物馆,人文", 0)],
    "南京": [("中山陵", "人文,户外", 0), ("夫子庙", "人文,夜景,美食", 0), ("总统府", "人文,近代史", 35), ("玄武湖公园", "城市,自然", 0), ("明孝陵", "世界遗产", 70), ("南京博物院", "博物馆,人文", 0)],
    "重庆": [("洪崖洞夜景", "夜景,城市", 0), ("武隆天生三桥", "户外,世界遗产", 95), ("解放碑步行街", "城市,美食", 0), ("磁器口古镇", "人文,美食", 0), ("长江索道", "城市,体验", 30), ("大足石刻", "世界遗产,人文", 115)],
}


def _airport_code(city: str) -> str:
    """3 字母机场代码 mock。"""
    return {
        "北京": "PEK",
        "上海": "PVG",
        "广州": "CAN",
        "深圳": "SZX",
        "成都": "CTU",
        "杭州": "HGH",
        "苏州": "SHA",  # 苏州没有民航,就近用 SHA
        "西安": "XIY",
        "南京": "NKG",
        "重庆": "CKG",
    }.get(city, "ZZZ")


def _seed_flights(session: Session) -> int:
    base_date = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=2)
    count = 0
    for origin in CITIES:
        for destination in CITIES:
            if origin == destination:
                continue
            # 每对城市每天 1-2 班随机
            for day_offset in range(0, 7):
                if random.random() > 0.35:
                    continue
                code, name = random.choice(AIRLINES)
                flight_no = f"{code}{random.randint(1000, 9999)}"
                hour = random.choice([7, 9, 11, 14, 16, 18, 20])
                departure = base_date + timedelta(days=day_offset, hours=hour - 8)
                arrival = departure + timedelta(hours=random.choice([2, 2, 3, 3, 4]))
                price = random.choice([580, 680, 880, 1080, 1280, 1580])
                total = random.choice([150, 180, 220])
                available = random.randint(max(1, total - 30), total)
                session.add(
                    Flight(
                        flight_no=flight_no,
                        airline=name,
                        origin=origin,
                        destination=destination,
                        departure_time=departure,
                        arrival_time=arrival,
                        price=float(price),
                        total_seats=total,
                        available_seats=available,
                        aircraft=random.choice(["A320", "A321", "B737", "B738"]),
                        status="scheduled",
                    )
                )
                count += 1
    return count


def _seed_one_demo_ticket(session: Session) -> int:
    """给 demo 用户预占一张票,方便 fetch_user_flight_information 演示。"""
    flight = session.query(Flight).filter(Flight.origin == "上海", Flight.destination == "成都").first()
    if not flight:
        return 0
    session.add(
        Ticket(
            ticket_no="WB2026" + str(random.randint(100000, 999999)),
            flight_id=flight.id,
            passenger_id="demo_user_001",
            seat="14A",
            status="active",
        )
    )
    return 1


def _seed_hotels(session: Session) -> int:
    count = 0
    for city in CITIES:
        for brand, tier, base_price, rating in HOTEL_BRANDS:
            name = f"{city}{brand}"
            price = base_price + random.randint(-40, 80)
            session.add(
                HotelInventory(
                    name=name,
                    location=city,
                    price_per_night=float(price),
                    price_tier=tier,
                    rating=rating,
                    description=f"{city}核心商圈,出行便利。",
                )
            )
            count += 1
    return count


def _seed_cars(session: Session) -> int:
    count = 0
    for city in CITIES:
        for company in CAR_COMPANIES:
            for vclass, rate, transmission in random.sample(CAR_CLASSES, k=3):
                session.add(
                    CarRental(
                        company=company,
                        location=city,
                        vehicle_class=vclass,
                        daily_rate=float(rate + random.randint(-30, 60)),
                        transmission=transmission,
                    )
                )
                count += 1
    return count


def _seed_trips(session: Session) -> int:
    count = 0
    for city, items in ATTRACTIONS.items():
        for name, keywords, price in items:
            session.add(
                TripRecommendation(
                    name=name,
                    location=city,
                    keywords=keywords,
                    description=f"{city}热门体验:{name}。",
                    price=float(price),
                    duration_hours=random.choice([1.5, 2.0, 3.0, 4.0, 0.5]),
                )
            )
            count += 1
    return count


def main() -> None:
    random.seed(20260514)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        # 清空(顺序:先 tickets 再 flights,避免外键约束)
        session.query(Ticket).delete()
        session.query(Flight).delete()
        session.query(HotelInventory).delete()
        session.query(CarRental).delete()
        session.query(TripRecommendation).delete()
        session.commit()

        n_f = _seed_flights(session)
        session.commit()
        n_t = _seed_one_demo_ticket(session)
        n_h = _seed_hotels(session)
        n_c = _seed_cars(session)
        n_r = _seed_trips(session)
        session.commit()

    print(f"已插入:flights={n_f}  tickets={n_t}  hotels={n_h}  cars={n_c}  trips={n_r}")


if __name__ == "__main__":
    main()
