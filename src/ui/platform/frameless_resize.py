"""Windows: edge/corner resize for frameless Qt windows (same behavior as MainShellWindow)."""

from __future__ import annotations

import ctypes
import sys
from typing import Any, Tuple

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QWidget

_HTLEFT = 10
_HTRIGHT = 11
_HTTOP = 12
_HTTOPLEFT = 13
_HTTOPRIGHT = 14
_HTBOTTOM = 15
_HTBOTTOMLEFT = 16
_HTBOTTOMRIGHT = 17
_WM_NCHITTEST = 0x0084
_EDGE = 8


def _read_wm_nchittest_lparam(msg_ptr: int) -> tuple[int, int] | None:
    if not msg_ptr:
        return None
    ps = ctypes.sizeof(ctypes.c_void_p)
    if ps == 8:
        msg_off, lparam_off = 8, 24
    else:
        msg_off, lparam_off = 4, 12
    try:
        mid = ctypes.c_uint32.from_address(msg_ptr + msg_off).value
        lp = ctypes.c_ssize_t.from_address(msg_ptr + lparam_off).value
    except OSError:
        return None
    return mid, int(lp)


def frameless_native_resize_event(
    widget: QWidget, eventType: Any, message: Any
) -> Tuple[bool, int]:
    if sys.platform != "win32":
        return False, 0
    try:
        et = bytes(eventType)
    except (TypeError, AttributeError):
        return False, 0
    if et != b"windows_generic_MSG":
        return False, 0
    try:
        addr = int(message)
    except (TypeError, ValueError, OverflowError):
        return False, 0
    parsed = _read_wm_nchittest_lparam(addr)
    if parsed is None:
        return False, 0
    mid, lp = parsed
    if mid != _WM_NCHITTEST:
        return False, 0
    x = ctypes.c_int16(lp & 0xFFFF).value
    y = ctypes.c_int16((lp >> 16) & 0xFFFF).value
    local = widget.mapFromGlobal(QPoint(x, y))
    m = _EDGE
    w, h = widget.width(), widget.height()
    on_l = local.x() < m
    on_r = local.x() >= w - m
    on_t = local.y() < m
    on_b = local.y() >= h - m

    if on_t and on_l:
        return True, _HTTOPLEFT
    if on_t and on_r:
        return True, _HTTOPRIGHT
    if on_b and on_l:
        return True, _HTBOTTOMLEFT
    if on_b and on_r:
        return True, _HTBOTTOMRIGHT
    if on_l:
        return True, _HTLEFT
    if on_r:
        return True, _HTRIGHT
    if on_t:
        return True, _HTTOP
    if on_b:
        return True, _HTBOTTOM

    return False, 0


class FramelessResizeMixin:
    """Mixin for QWidget subclasses using Qt.FramelessWindowHint; enables drag-resize on Windows."""

    def nativeEvent(self, eventType, message):  # noqa: N802
        handled, res = frameless_native_resize_event(self, eventType, message)
        if handled:
            return True, res
        try:
            return super().nativeEvent(eventType, message)  # type: ignore[misc]
        except AttributeError:
            return False, 0
