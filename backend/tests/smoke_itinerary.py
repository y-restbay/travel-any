"""烟雾测试:走一遍 generate_itinerary_summary + export_itinerary 的纯函数路径。

不打 LLM、不起 HTTP,只验证 handler 能拿到 store 中的行程并真的把文件写到磁盘。
跑法:
    cd backend && source .venv/bin/activate && python -m tests.smoke_itinerary
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许从 backend/ 直接 python 这个文件
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.travel_tools.export_tool import handle_export_itinerary, EXPORT_DIR  # noqa: E402
from app.travel_tools.itinerary_store import clear_all  # noqa: E402
from app.travel_tools.itinerary_tool import handle_generate_itinerary_summary  # noqa: E402


SAMPLE = {
    "trip_title": "苏州三日游",
    "trip_dates": "2026-06-01 至 2026-06-03",
    "summary": "围绕苏州古城核心区与园林展开的 3 天慢节奏行程,兼顾人文与美食。",
    "meta": {
        "destination": "苏州",
        "people": "2 人",
        "budget": "中等",
        "accommodation": "观前街附近精品酒店",
        "preferences": "园林、苏帮菜",
        "transport_mode": "地铁 + 步行",
    },
    "weather_summary": [
        {"date": "06-01", "condition": "多云", "temp": "22-29°C", "tip": "适合户外"},
        {"date": "06-02", "condition": "小雨", "temp": "20-26°C", "tip": "记得带伞"},
        {"date": "06-03", "condition": "晴", "temp": "23-30°C", "tip": "注意防晒"},
    ],
    "days": [
        {
            "day_number": 1,
            "title": "园林经典",
            "theme": "拙政园 + 狮子林 + 观前夜市",
            "schedule": [
                {"time": "09:00", "type": "depart", "place": "酒店", "note": "步行至地铁"},
                {
                    "time": "09:30",
                    "type": "visit",
                    "place": "拙政园",
                    "duration_min": 150,
                    "ticket": 90,
                    "highlights": ["远香堂", "见山楼"],
                },
                {"time": "12:00", "type": "meal", "place": "得月楼", "cuisine": "苏帮菜", "must_try": ["松鼠桂鱼", "响油鳝糊"], "cost": 180},
                {"time": "14:00", "type": "visit", "place": "狮子林", "ticket": 40, "tips": "假山很巧"},
                {"time": "17:00", "type": "transit", "from": "狮子林", "to": "观前街", "duration_min": 20},
            ],
            "day_cost": {"tickets": 130, "meals": 180, "transport": 15, "total": 325},
        },
        {
            "day_number": 2,
            "title": "古镇与水路",
            "theme": "平江路 + 山塘街",
            "schedule": [
                {"time": "10:00", "type": "visit", "place": "平江路", "duration_min": 120},
                {"time": "12:30", "type": "meal", "place": "陆稿荐", "cost": 120},
                {"time": "15:00", "type": "visit", "place": "山塘街", "duration_min": 120},
            ],
            "day_cost": {"tickets": 0, "meals": 120, "transport": 10, "total": 130},
        },
        {
            "day_number": 3,
            "title": "虎丘与返程",
            "theme": "虎丘 + 返程",
            "schedule": [
                {"time": "09:00", "type": "visit", "place": "虎丘", "ticket": 80},
                {"time": "12:00", "type": "meal", "place": "松鹤楼", "cost": 200},
                {"time": "15:00", "type": "return", "place": "苏州站"},
            ],
            "day_cost": {"tickets": 80, "meals": 200, "transport": 25, "total": 305},
        },
    ],
    "total_budget": {"tickets": 210, "meals": 500, "transport": 50, "accommodation": 1200, "total": 1960},
    "important_notes": [
        "园林周末客流大,建议提前在公众号订票",
        "雨天滑石路,园林石板路注意脚下",
        "苏州地铁支持云闪付扫码,准备一张实体卡更稳",
    ],
}


def main() -> None:
    clear_all()
    summary, payload = handle_generate_itinerary_summary(SAMPLE, session_id="smoke-session")
    print("== generate 返回 LLM ==", summary)
    assert summary.get("状态") == "success", summary
    itin_id = summary["itinerary_id"]
    assert payload and payload["itinerary_id"] == itin_id
    assert len(payload["days"]) == 3

    pdf_summary, pdf_payload = handle_export_itinerary({"itinerary_id": itin_id, "format": "pdf"})
    print("== export pdf 返回 LLM ==", pdf_summary)
    assert pdf_summary.get("状态") == "success", pdf_summary
    pdf_path = EXPORT_DIR / f"{itin_id}.pdf"
    assert pdf_path.is_file() and pdf_path.stat().st_size > 0
    print("PDF 路径:", pdf_path, "大小:", pdf_path.stat().st_size)

    docx_summary, docx_payload = handle_export_itinerary({"itinerary_id": itin_id, "format": "docx"})
    print("== export docx 返回 LLM ==", docx_summary)
    assert docx_summary.get("状态") == "success", docx_summary
    docx_path = EXPORT_DIR / f"{itin_id}.docx"
    assert docx_path.is_file() and docx_path.stat().st_size > 0
    print("DOCX 路径:", docx_path, "大小:", docx_path.stat().st_size)

    # 幂等:再调一次 pdf,文件 mtime 不变
    before_mtime = pdf_path.stat().st_mtime
    handle_export_itinerary({"itinerary_id": itin_id, "format": "pdf"})
    after_mtime = pdf_path.stat().st_mtime
    assert before_mtime == after_mtime, "幂等失败:文件被重写"
    print("幂等检查通过")

    # 错误路径:不存在的 itinerary_id
    err_summary, err_payload = handle_export_itinerary({"itinerary_id": "itin_nonexistent", "format": "pdf"})
    print("== 错误路径 ==", err_summary)
    assert "error" in err_summary
    assert err_payload is None

    print("\n全部烟雾测试通过 ✓")


if __name__ == "__main__":
    main()
