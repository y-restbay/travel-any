"""图片上传接口。前端把图片发到这里,拿到 image_ref 后随聊天消息一起送出。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.image_store import get_image_store


router = APIRouter(prefix="/upload", tags=["upload"])
logger = logging.getLogger("app.upload")


_ALLOWED_MIMES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/heic",
    "image/heif",
}
_MAX_MB = 50
_MAX_BYTES = _MAX_MB * 1024 * 1024
_EXTENSION_MIMES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def _normalize_mime(content_type: str | None, filename: str | None) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime and mime != "application/octet-stream":
        return mime
    suffix = Path(filename or "").suffix.lower()
    return _EXTENSION_MIMES.get(suffix, mime)


@router.post("/image")
async def upload_image(file: UploadFile = File(...)) -> dict:
    """接收一张图片,缓存到进程内,返回 image_ref 供后续聊天消息携带。

    - 类型限制: JPEG/PNG/WebP/GIF/BMP/HEIC
    - 大小限制: 50 MB
    - TTL: 1 小时,过期自动清理
    """
    mime = _normalize_mime(file.content_type, file.filename)
    if mime not in _ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的图片类型: {mime or '未知'}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="图片内容为空",
        )
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"图片过大: {len(data) // 1024} KB,超过 {_MAX_MB} MB 限制",
        )

    ref = get_image_store().put(data, mime=mime)
    logger.info(
        "上传图片 | ref=%s | %s | %d KB | name=%s",
        ref,
        mime,
        len(data) // 1024,
        file.filename or "(未命名)",
    )
    return {"image_ref": ref, "size_bytes": len(data), "mime": mime}
