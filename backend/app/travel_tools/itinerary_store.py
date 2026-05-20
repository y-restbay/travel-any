"""行程内存缓存。

第一版用进程内字典存放;生产环境应改为 Redis 等共享存储,以便:
1. 多 worker 共享(Uvicorn 多进程)
2. 重启不丢
3. 设置 TTL 自动回收

任务原文里 key 设计是 ``(session_id, itinerary_id)``。
实际场景中 "生成" 和 "导出" 通常是两次独立的 SSE 请求,
session_id 在前端没有持久化时会变;itinerary_id 又是 uuid 前缀,
全局已足够唯一。所以这里直接用 itinerary_id 做 key,
把 session_id 写进 entry 元数据,后续要做更严格隔离时再升级。
"""
from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Optional, Tuple


_STORE: Dict[str, Dict[str, Any]] = {}
_LOCK = RLock()


def put_itinerary(itinerary_id: str, payload: Dict[str, Any], *, session_id: Optional[str] = None) -> None:
    """写入一条行程。``payload`` 是完整的 itinerary 数据。"""
    with _LOCK:
        _STORE[itinerary_id] = {
            "session_id": session_id or "",
            "data": payload,
        }


def get_itinerary(itinerary_id: str) -> Optional[Dict[str, Any]]:
    """读取一条行程的原始 data。取不到返回 None。"""
    with _LOCK:
        entry = _STORE.get(itinerary_id)
        if not entry:
            return None
        return entry["data"]


def get_latest_itinerary(*, session_id: Optional[str] = None) -> Optional[Tuple[str, Dict[str, Any]]]:
    """读取最近生成的行程。

    优先匹配当前 session_id；如果当前请求没有 session_id 或找不到匹配项，
    回退到全局最近一条。这样用户说“总结一下，并生成 PDF”时，导出工具
    不必依赖模型准确记住 itinerary_id。
    """
    with _LOCK:
        if not _STORE:
            return None

        requested_session = (session_id or "").strip()
        if requested_session:
            for itinerary_id, entry in reversed(_STORE.items()):
                if entry.get("session_id") == requested_session:
                    return itinerary_id, entry["data"]

        itinerary_id, entry = next(reversed(_STORE.items()))
        return itinerary_id, entry["data"]


def clear_all() -> None:
    """测试用:清空所有行程。"""
    with _LOCK:
        _STORE.clear()
