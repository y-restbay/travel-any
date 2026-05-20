"""旅行助手专用工具集合：天气查询、路径规划、行程汇总、导出与图片识景。"""

from app.travel_tools.directions_tool import (
    DIRECTIONS_TOOL_SCHEMA,
    handle_get_directions,
)
from app.travel_tools.itinerary_store import get_itinerary, put_itinerary
from app.travel_tools.landmark_tool import (
    LANDMARK_TOOL_DESCRIPTION,
    LANDMARK_TOOL_SCHEMA,
    handle_identify_landmark,
)
from app.travel_tools.realtime_search_tool import (
    REALTIME_SEARCH_TOOL_SCHEMA,
    handle_realtime_search,
)
from app.travel_tools.weather_tool import (
    WEATHER_TOOL_SCHEMA,
    get_weather,
)

__all__ = [
    "WEATHER_TOOL_SCHEMA",
    "get_weather",
    "DIRECTIONS_TOOL_SCHEMA",
    "handle_get_directions",
    "REALTIME_SEARCH_TOOL_SCHEMA",
    "handle_realtime_search",
    "LANDMARK_TOOL_SCHEMA",
    "LANDMARK_TOOL_DESCRIPTION",
    "handle_identify_landmark",
    "get_itinerary",
    "put_itinerary",
]
