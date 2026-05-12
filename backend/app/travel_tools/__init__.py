"""旅行助手专用工具集合：天气查询等。"""

from app.travel_tools.weather_tool import (
    WEATHER_TOOL_SCHEMA,
    get_weather,
)

__all__ = ["WEATHER_TOOL_SCHEMA", "get_weather"]
