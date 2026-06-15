"""多模态(VLM)客户端,统一封装图片识别调用。

当前实现使用阿里百炼的 OpenAI 兼容模式,默认模型 qwen-vl-max。
配置来源优先级:
1. 显式传入构造参数
2. vlm_configs 表里 is_active=True 的记录
3. 环境变量(api_key 回退到 DASHSCOPE_API_KEY,base_url 回退到百炼默认端点)

VLM 配置与文本调度模型的 LLMConfig 分离,因此修改 VLM 不会影响 DeepSeek 等文本模型。
"""
from __future__ import annotations

import os
from typing import Optional

from app.travel_tools.image_utils import to_data_url


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.6-flash"
DEFAULT_TIMEOUT = 60.0


class VLMClient:
    """轻量 VLM 包装,只暴露一个 recognize 入口。"""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = (api_key or "").strip() or os.getenv("DASHSCOPE_API_KEY", "").strip()
        self.base_url = (base_url or "").strip() or DEFAULT_BASE_URL
        self.model = (model or "").strip() or DEFAULT_MODEL
        self.timeout = timeout

    def is_ready(self) -> bool:
        return bool(self.api_key)

    async def recognize(self, image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
        """调用 VLM 识别图片,返回模型文本输出(可能含 markdown / JSON)。"""
        if not self.is_ready():
            raise RuntimeError(
                "未配置 VLM API Key。请在管理后台 / .env 设置 DASHSCOPE_API_KEY,"
                "或在 VLM 配置里填写 api_key。"
            )

        # openai SDK 已经被 langchain-openai 间接依赖,直接 import 即可。
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": to_data_url(image_bytes, mime=mime)},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
        )
        if not response.choices:
            return ""
        message = response.choices[0].message
        content = getattr(message, "content", "") or ""
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or ""))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)


def build_vlm_client_from_config(config) -> VLMClient:
    """根据 VLMConfig ORM 记录构造客户端;空字段回退到环境变量/默认值。"""
    return VLMClient(
        api_key=getattr(config, "api_key", "") or "",
        base_url=getattr(config, "base_url", "") or "",
        model=getattr(config, "model_name", "") or "",
    )
