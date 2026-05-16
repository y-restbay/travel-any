"""4 个专家子 agent 的工具集与 prompt 模板。

每个 specialist 用 create_react_agent 直接构造,跑完后通过 StateGraph
的 add_edge(<sub>, "supervisor") 把控制权交回 supervisor。
"""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from app.travel_tools.car_tool import (
    book_car_rental,
    cancel_car_rental,
    search_car_rentals,
    update_car_rental,
)
from app.travel_tools.flights_booking_tool import (
    cancel_ticket,
    fetch_user_flight_information,
    search_flights,
    update_ticket_to_new_flight,
)
from app.travel_tools.hotels_booking_tool import (
    book_hotel,
    cancel_hotel,
    search_hotels_inventory,
    update_hotel_booking,
)
from app.travel_tools.trip_recommend_tool import (
    book_excursion,
    cancel_excursion,
    search_trip_recommendations,
    update_excursion,
)


FLIGHT_AGENT_PROMPT = (
    "你是航班专家 (flight_agent)。"
    "你的职责仅限于:查询航班、查询用户已购票、改签、取消机票。"
    "不要回答酒店、租车、景点、天气、路线规划等其他问题。"
    "完成任务或者发现请求不属于你的范围后,请直接给出最终回答,不要继续调用工具,系统会把控制权交回主助理。"
    "对改签 / 取消等敏感操作,工具内部已会请求用户确认,你直接调用即可。"
)

HOTEL_AGENT_PROMPT = (
    "你是酒店预订专家 (hotel_agent)。"
    "职责:基于本地酒店库存(hotels_inventory)查询、预订、修改、取消。"
    "不处理航班、租车、景点、天气、路线。完成任务后给出最终回答,不要继续调工具。"
    "需要预订城市、入住 / 退房日期,缺少时先问用户。"
)

CAR_AGENT_PROMPT = (
    "你是租车专家 (car_agent)。职责:查询、预订、修改、取消租车。"
    "不处理航班 / 酒店 / 景点 / 天气 / 路线。完成后给出最终回答。"
    "预订时需要城市、起止日期,缺少时先问用户。"
)

TRIP_AGENT_PROMPT = (
    "你是景点门票 / 旅游产品专家 (trip_agent)。"
    "职责:查询、预订、修改、取消旅游产品 / 景点门票(基于本地库存 trip_recommendations)。"
    "不处理整段行程规划(那是主助理的 generate_itinerary_summary 工具)。"
    "完成任务或遇到非本范围请求时,给出最终回答即可。"
)


SPECIALIST_DEFINITIONS = [
    {
        "name": "flight_agent",
        "prompt": FLIGHT_AGENT_PROMPT,
        "tools": [
            search_flights,
            fetch_user_flight_information,
            update_ticket_to_new_flight,
            cancel_ticket,
        ],
        "handoff_description": (
            "把任务转交给航班专家。适用于:查询航班、查看已购票、改签、退票。"
            "调用时请把所有相关上下文(城市、日期、票号、用户偏好等)写到 task_description。"
        ),
    },
    {
        "name": "hotel_agent",
        "prompt": HOTEL_AGENT_PROMPT,
        "tools": [
            search_hotels_inventory,
            book_hotel,
            update_hotel_booking,
            cancel_hotel,
        ],
        "handoff_description": (
            "把任务转交给酒店预订专家。适用于:酒店库存查询、预订、改期、取消。"
            "如果用户只是问'某地有什么酒店推荐'(POI),仍由主助理处理,不必转交。"
        ),
    },
    {
        "name": "car_agent",
        "prompt": CAR_AGENT_PROMPT,
        "tools": [
            search_car_rentals,
            book_car_rental,
            update_car_rental,
            cancel_car_rental,
        ],
        "handoff_description": "把任务转交给租车专家:查找可租车辆、预订、改期、取消。",
    },
    {
        "name": "trip_agent",
        "prompt": TRIP_AGENT_PROMPT,
        "tools": [
            search_trip_recommendations,
            book_excursion,
            update_excursion,
            cancel_excursion,
        ],
        "handoff_description": (
            "把任务转交给旅游产品 / 景点门票专家。适用于:基于库存预订单个景点 / 一日游。"
            "整段行程规划仍由主助理用 generate_itinerary_summary 完成,不必转交。"
        ),
    },
]


def build_specialists(model):
    """为每个 specialist 创建一个 react_agent;追加全局风格守则。"""
    # 延迟 import 避免与 chat_service 的潜在循环
    from app.services.chat_service import STYLE_GUIDELINES

    agents = {}
    for d in SPECIALIST_DEFINITIONS:
        full_prompt = f"{d['prompt']}\n\n{STYLE_GUIDELINES}"
        agents[d["name"]] = create_react_agent(
            model=model,
            tools=d["tools"],
            prompt=full_prompt,
            name=d["name"],
        )
    return agents
