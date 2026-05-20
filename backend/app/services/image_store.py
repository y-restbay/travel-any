"""进程内临时图片存储。

图片以原始字节缓存在内存里,按 image_ref 取出后给 VLM 工具使用。
- TTL 默认 1 小时,过期自动剔除
- 进程重启会丢失,适合开发环境;上线可换 Redis / 对象存储
- 单进程足够,FastAPI uvicorn 单 worker 下不会有竞态
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional


DEFAULT_TTL_SECONDS = 3600  # 1 小时


@dataclass
class _Entry:
    data: bytes
    mime: str
    expires_at: float


class ImageStore:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._items: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def put(self, data: bytes, mime: str = "image/jpeg") -> str:
        ref = "img_" + uuid.uuid4().hex[:16]
        with self._lock:
            self._items[ref] = _Entry(data=data, mime=mime, expires_at=time.time() + self._ttl)
        return ref

    def get(self, ref: str) -> Optional[tuple[bytes, str]]:
        with self._lock:
            entry = self._items.get(ref)
            if entry is None:
                return None
            if entry.expires_at < time.time():
                self._items.pop(ref, None)
                return None
            return entry.data, entry.mime

    def sweep(self) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            for key in list(self._items.keys()):
                if self._items[key].expires_at < now:
                    self._items.pop(key, None)
                    removed += 1
        return removed


_store: Optional[ImageStore] = None


def get_image_store() -> ImageStore:
    global _store
    if _store is None:
        _store = ImageStore()
    return _store
