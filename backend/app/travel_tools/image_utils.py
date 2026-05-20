"""图片预处理工具:压缩 + base64 编码,降低 VLM 调用的成本和延迟。"""
from __future__ import annotations

import base64
import io


def compress_image(image_bytes: bytes, max_edge: int = 1280, quality: int = 80) -> bytes:
    """长边缩放到 max_edge 以内,转 JPEG/quality=80,去 EXIF。

    Pillow 是惰性 import,因为只有上传图片的请求才需要它,
    避免后端常驻进程多吃几 MB 内存。
    """
    from PIL import Image  # noqa: WPS433

    with Image.open(io.BytesIO(image_bytes)) as img:
        # 触发解码并丢掉 EXIF
        img.load()
        if img.mode not in {"RGB", "L"}:
            img = img.convert("RGB")

        w, h = img.size
        longest = max(w, h)
        if longest > max_edge:
            ratio = max_edge / longest
            new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
            img = img.resize(new_size, Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()


def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{image_to_base64(image_bytes)}"
