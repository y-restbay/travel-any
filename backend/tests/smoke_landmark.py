"""真实 VLM 烟雾测试:对几类典型"不可信"图片验证 qwen-vl-max 是否守住护栏。

不是 pytest(命名不以 test_ 开头),pytest 不会自动收集。
**会真的调用 qwen-vl-max,消耗 API 额度**。

跑法:
    cd backend && source .venv/bin/activate && python -m tests.smoke_landmark

可选参数:
    python -m tests.smoke_landmark path/to/your_landmark.jpg
        如果传入文件路径,会额外测一张真实图片。

预期输出三类:
    case_blank   纯灰图        → 期望 状态=uncertain/failed,绝不能编造景点名
    case_noise   随机彩色噪声  → 同上
    case_misleading_text  含"故宫"字样的纯色图 → 看 VLM 是否被文字骗
    [可选] real_landmark   真实地标照片  → 期望 状态=success 且与图相符
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

from app.services.image_store import get_image_store  # noqa: E402
from app.travel_tools.landmark_tool import handle_identify_landmark  # noqa: E402
from app.travel_tools.vlm_client import VLMClient  # noqa: E402


def _make_blank(color=(120, 120, 120)) -> bytes:
    img = Image.new("RGB", (640, 480), color=color)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_noise() -> bytes:
    import random

    img = Image.new("RGB", (320, 240))
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            pixels[x, y] = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _make_misleading_text(text: str = "故宫") -> bytes:
    """纯色背景上写一个误导性的文字。考验 VLM 是否会因为文字就自信地说是某景点。"""
    img = Image.new("RGB", (640, 480), color=(200, 200, 220))
    draw = ImageDraw.Draw(img)
    draw.text((240, 220), text, fill=(40, 40, 80))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _print_result(case: str, result: dict) -> None:
    print(f"\n===== {case} =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _flag(case: str, result: dict, expect_uncertain: bool) -> None:
    """简单判定:不可信图片必须 uncertain/failed;真实地标必须 success。"""
    status = result.get("状态", "")
    if expect_uncertain:
        if status in {"uncertain", "failed"}:
            print(f"  ✅ {case}: 守住护栏 (状态={status})")
        else:
            print(f"  ❌ {case}: 护栏失守! VLM 对不可信图片返回 {status},可能编造")
    else:
        if status == "success":
            print(f"  ✅ {case}: 真实地标识别成功")
        else:
            print(f"  ⚠️  {case}: 真实地标未识别为 success (status={status})")


async def main() -> None:
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("❌ 未设置 DASHSCOPE_API_KEY,无法跑 smoke。请检查 backend/.env。")
        sys.exit(2)

    store = get_image_store()
    vlm = VLMClient()
    print(f"VLM 配置: model={vlm.model} base_url={vlm.base_url}")

    cases = [
        ("case_blank_gray", _make_blank(), True),
        ("case_random_noise", _make_noise(), True),
        ("case_misleading_text_故宫", _make_misleading_text("故宫"), True),
    ]

    if len(sys.argv) > 1:
        real_path = Path(sys.argv[1])
        if real_path.exists():
            cases.append(("real_landmark_" + real_path.name, real_path.read_bytes(), False))
        else:
            print(f"⚠️  传入的图片路径不存在: {real_path}")

    for case, image_bytes, expect_uncertain in cases:
        ref = store.put(image_bytes, mime="image/jpeg")
        try:
            result = await handle_identify_landmark(
                {"image_ref": ref, "user_question": "这是哪里?"},
                vlm_client=vlm,
            )
        except Exception as exc:
            print(f"\n===== {case} =====")
            print(f"❌ 工具抛异常(不该发生): {exc.__class__.__name__}: {exc}")
            continue
        _print_result(case, result)
        _flag(case, result, expect_uncertain)


if __name__ == "__main__":
    asyncio.run(main())
