"""图片识别景点工具 (identify_landmark)。

由文本调度 LLM (DeepSeek 等) 通过 function call 触发,
后端拿到 image_ref 后:
1. 从临时存储取出图片字节
2. 压缩 + base64
3. 喂给 VLM (qwen-vl-max),要求严格 JSON 输出
4. 解析后回传结构化结果给主调度 LLM,由它继续编排其他工具
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from app.services.image_store import get_image_store
from app.travel_tools.image_utils import compress_image
from app.travel_tools.vlm_client import VLMClient


LANDMARK_TOOL_DESCRIPTION = (
    "识别用户在本轮对话中上传的图片里的景点或地标。"
    "当用户消息携带 image_ref 时(代表他上传了一张图片),必须先调用此工具。"
    "识别成功后,你可以继续调用 search_realtime_travel_info / get_weather / "
    "get_directions 等工具,为用户补充该景点的介绍、天气、周边和路线。"
    "工具内部使用国内多模态大模型(qwen-vl-max),你只需传入 image_ref。"
)


# 防幻觉 prompt：强约束 + JSON 输出。所有"宁可不确定也不要编造"的要求在这里集中。
LANDMARK_RECOGNITION_PROMPT = """\
你是一个专业的景点识别助手。请仔细观察这张图片,识别其中的景点或地标。

请严格按以下步骤思考:
1. 先描述你在图片中看到的关键特征:建筑风格、自然环境、标志性元素、
   文字招牌(如有)。
2. 基于这些特征,判断这可能是哪个景点。
3. 评估你的确定程度。

重要原则:
- 如果你能确定具体景点(如知名地标),明确给出名称和所在城市。
- 如果你不确定具体是哪一个,绝不要猜测编造名称。诚实地描述图片特征,
  说明它"可能属于某类景点"(例如"江南古典园林""藏传佛教寺庙"),
  并说明无法确定具体名称。
- 如果图片主要是人物,不要识别人脸,只说明"这张图主要是人物,
  我专注于识别景点和地标"。
- 宁可说"不确定",也不要给出错误的肯定答案。

请只输出一个 JSON 对象,不要任何 markdown 包裹、不要解释文字,字段如下:
{
  "landmark_name": "景点名称,不确定时为空字符串",
  "city": "所在城市,不确定时为空字符串",
  "confidence": "高 | 中 | 低",
  "features": "你观察到的关键视觉特征,简要描述",
  "reasoning": "你判断的依据;不确定时说明无法确定的原因",
  "is_person_focused": false
}

约束:
- 当 landmark_name 非空时,confidence 必须是"高"或"中",且 city 也应当尽量填写。
- 当 confidence 为"低"或 landmark_name 为空时,绝不要让回答呈现确定性。
- is_person_focused=true 时,其他字段允许为空,只需 features 简述图中人物存在即可。
"""


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)


def _safe_parse_json(raw: str) -> Dict[str, Any]:
    """VLM 偶尔会输出 ```json``` 包裹的代码块或带前后说明文字,尽量稳健解析。"""
    if not raw:
        return {}
    text = raw.strip()

    # 1) ```json {...} ``` 包裹
    match = _JSON_BLOCK_RE.search(text)
    if match:
        candidate = match.group(1).strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 2) 直接解析
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 3) 截取第一个 { 到最后一个 } 之间
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return {}


async def handle_identify_landmark(
    args: Dict[str, Any],
    *,
    vlm_client: Optional[VLMClient] = None,
) -> Dict[str, Any]:
    """工具 handler。返回结构化中文 dict,绝不抛异常。"""
    image_ref = (args.get("image_ref") or "").strip()
    user_question = (args.get("user_question") or "").strip()

    if not image_ref:
        return {
            "状态": "failed",
            "错误": "缺少 image_ref 参数,无法读取图片",
            "提示": "如果用户没有上传图片,请直接回复用户'我没有看到图片,请重新上传'。",
        }

    # 1. 取图
    record = get_image_store().get(image_ref)
    if record is None:
        return {
            "状态": "failed",
            "错误": "图片不存在或已过期(临时缓存 TTL 1 小时)",
            "提示": "请提示用户重新上传图片后再次提问。",
        }
    image_bytes, mime = record

    # 2. 压缩,长边 1280 / JPEG 80
    try:
        compressed = compress_image(image_bytes)
        compressed_mime = "image/jpeg"
    except Exception as exc:
        return {
            "状态": "failed",
            "错误": f"图片处理失败: {exc.__class__.__name__}: {exc}",
        }

    # 3. 调 VLM
    client = vlm_client or VLMClient()
    if not client.is_ready():
        return {
            "状态": "failed",
            "错误": "未配置 VLM(qwen-vl-max)的 API Key",
            "提示": "请在管理后台「图片识别模型」里配置,或设置 DASHSCOPE_API_KEY。",
        }

    prompt = LANDMARK_RECOGNITION_PROMPT
    if user_question:
        prompt += f"\n\n用户的问题(辅助参考,不要直接采纳为景点名):{user_question}"

    try:
        raw = await client.recognize(compressed, prompt, mime=compressed_mime)
    except Exception as exc:
        return {
            "状态": "failed",
            "错误": f"识别服务异常: {exc.__class__.__name__}: {exc}",
            "提示": "请稍后再试,或检查 VLM 配置/网络。",
        }

    # 4. 解析 VLM JSON
    parsed = _safe_parse_json(raw)
    if not parsed:
        return {
            "状态": "failed",
            "错误": "VLM 返回的内容无法解析为 JSON",
            "原始输出": raw[:600],
            "提示": "建议你向用户说明识别失败,询问该景点大致在哪个城市以缩小范围。",
        }

    # 5. 组装回复给主调度 LLM
    if parsed.get("is_person_focused"):
        return {
            "状态": "uncertain",
            "提示": "图片主要是人物。请告诉用户:'这张图主要是人物,我只识别景点和地标,请提供景点照片。'",
            "图片特征": parsed.get("features", ""),
        }

    confidence = str(parsed.get("confidence") or "").strip()
    landmark = str(parsed.get("landmark_name") or "").strip()
    city = str(parsed.get("city") or "").strip()
    features = str(parsed.get("features") or "").strip()
    reasoning = str(parsed.get("reasoning") or "").strip()

    # 防幻觉兜底:即使 VLM 给了名字,但置信度低或缺城市,降级为不确定。
    is_confident = bool(landmark) and confidence in {"高", "中"}

    if is_confident:
        return {
            "状态": "success",
            "景点名称": landmark,
            "所在城市": city,
            "置信度": confidence,
            "图片特征": features,
            "判断依据": reasoning,
            "提示": (
                "已识别景点。后续步骤建议:"
                "1) 用 search_realtime_travel_info 查该景点最新介绍 / 开放时间;"
                "2) 用 get_weather 查所在城市天气;"
                "3) 如果用户希望规划行程,可调用 get_directions / generate_itinerary_summary。"
                "回答用户时直接说出景点名称和城市,不要复述本工具的字段名。"
            ),
        }

    return {
        "状态": "uncertain",
        "图片特征": features,
        "推测": reasoning or "无法确定具体景点",
        "建议": (
            "不要编造景点名。请用自然语言告诉用户你看到的视觉特征,"
            "并礼貌询问该景点大致在哪个城市/地区,以便缩小范围。"
            "示例:'从图片看,这像是一座 XX 风格的建筑,但我不能完全确定。"
            "你能告诉我它大概在哪个城市吗?'"
        ),
    }


LANDMARK_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "identify_landmark",
        "description": LANDMARK_TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "image_ref": {
                    "type": "string",
                    "description": "用户消息里的图片引用 ID(形如 img_xxx),由前端上传图片时由后端分配",
                },
                "user_question": {
                    "type": "string",
                    "description": "用户随图片提出的文字问题(可选),用于辅助识别",
                },
            },
            "required": ["image_ref"],
        },
    },
}
