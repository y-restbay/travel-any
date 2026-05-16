"""进程内运行日志环形缓冲 + logging.Handler。

挂到 root logger 后,全应用 ``logging.getLogger(__name__)`` 的输出
(各工具的 warning / exception 等)都会被捕获,供 admin「日志管理」查看。

进程内、重启即清空——这是「运行日志查看器」,不是审计库。
要跨重启持久化,后续可加一张 DB 表,本模块对外接口形态不变。
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Deque, Dict, List, Optional

_MAX = 1000
_buffer: Deque[Dict[str, Any]] = deque(maxlen=_MAX)
_lock = threading.Lock()
_seq = 0

_LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class RingBufferHandler(logging.Handler):
    """把日志记录塞进进程内环形缓冲;绝不因格式化失败影响业务。"""

    def emit(self, record: logging.LogRecord) -> None:
        global _seq
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg = f"{msg}\n{self.formatException(record.exc_info)}"
        except Exception:
            msg = str(getattr(record, "msg", ""))
        with _lock:
            _seq += 1
            _buffer.append(
                {
                    "id": _seq,
                    "ts": record.created,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": msg,
                }
            )


_installed = False


def install_log_buffer(level: int = logging.INFO) -> None:
    """幂等:把环形缓冲 handler 挂到 root logger。"""
    global _installed
    if _installed:
        return
    handler = RingBufferHandler()
    handler.setLevel(level)
    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    root.addHandler(handler)
    _installed = True


def get_logs(
    *,
    level: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """按等级阈值 + 关键词过滤,返回最新在前的日志。"""
    with _lock:
        items = list(_buffer)

    if level and level.upper() != "ALL":
        threshold = _LEVEL_ORDER.get(level.upper(), 0)
        items = [r for r in items if _LEVEL_ORDER.get(r["level"], 0) >= threshold]

    if query:
        q = query.lower()
        items = [
            r for r in items if q in r["message"].lower() or q in r["logger"].lower()
        ]

    items = items[-limit:]
    items.reverse()  # 最新在前
    return items


def clear_logs() -> None:
    with _lock:
        _buffer.clear()
