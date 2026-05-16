"""行程导出文件下载端点。

只暴露 ``GET /api/exports/{filename}``;文件由 export 工具生成在 ``backend/storage/exports/``。
做路径穿越防护:用 resolve() 检查最终路径仍在 EXPORT_DIR 之内。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.travel_tools.export_tool import EXPORT_DIR

router = APIRouter(prefix="/exports", tags=["exports"])


_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{filename}")
async def download_export(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    target = (EXPORT_DIR / filename).resolve()
    try:
        target.relative_to(EXPORT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid path")

    if not target.is_file():
        raise HTTPException(status_code=404, detail="export not found")

    media_type = _MEDIA_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(path=str(target), media_type=media_type, filename=target.name)
