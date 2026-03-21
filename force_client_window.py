# -*- coding: utf-8 -*-
"""
窗口化游戏：将窗口「客户区」强制为标定尺寸（默认 1606×917，与 capture_client_resolution 实测一致）。

依赖（用 pip 安装第三方库）：
    pip install pywin32

用法：
    python force_client_window.py
    python force_client_window.py -W 1606 -H 917

窗口定位与 gf2_bot.find_game_window_rect 一致：标题包含 WINDOW_TITLE_KEYWORDS 之一。

说明：
- 改的是窗口几何尺寸，不是游戏内渲染分辨率；若游戏每帧改回尺寸，需在游戏里关闭锁定窗口等选项。
- 若游戏以管理员运行，请用管理员终端运行本脚本。
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes

try:
    import win32gui
except ImportError:
    print("请先安装: pip install pywin32", file=sys.stderr)
    sys.exit(1)

try:
    from gf2_bot import WINDOW_TITLE_KEYWORDS
except ImportError:
    WINDOW_TITLE_KEYWORDS = ["少女前线2", "GF2_Exilium"]

# GUI / CLI 共用的默认客户区目标（与 capture_client_resolution 实测一致）
DEFAULT_FORCE_CLIENT_W = 1606
DEFAULT_FORCE_CLIENT_H = 917


def find_game_hwnd() -> int | None:
    """
    与 gf2_bot.find_game_window_rect 相同规则：
    EnumWindows + GetWindowTextW，标题包含 WINDOW_TITLE_KEYWORDS 之一，
    且可见、客户区宽高为正；命中多个时取枚举顺序中最后一次（与 bot 一致）。
    """
    user32 = ctypes.windll.user32
    title_hits: list[int] = []
    last_hwnd: int | None = None

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    def callback(hwnd, lparam):
        nonlocal last_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        low_title = title.lower()
        if any(k.lower() in low_title for k in WINDOW_TITLE_KEYWORDS):
            rect = RECT()
            if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
                return True
            w = int(rect.right - rect.left)
            h = int(rect.bottom - rect.top)
            if w <= 0 or h <= 0:
                return True
            title_hits.append(1)
            last_hwnd = int(hwnd) if hwnd else None
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return last_hwnd if title_hits else None


def _get_client_size(hwnd: int) -> tuple[int, int]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return right - left, bottom - top


class _RECT(ctypes.Structure):
    _fields_ = (
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    )


def _adjust_window_rect_ex(
    client_w: int, client_h: int, style: int, exstyle: int
) -> tuple[int, int, int, int]:
    """
    pywin32 的 win32gui 未暴露 AdjustWindowRectEx，此处用 ctypes 调用 user32。
    输入客户区 (0,0)-(client_w, client_h)，返回外框 (left, top, right, bottom)。
    """
    user32 = ctypes.windll.user32
    rect = _RECT(0, 0, client_w, client_h)
    ok = user32.AdjustWindowRectEx(
        ctypes.byref(rect),
        wintypes.DWORD(style),
        wintypes.BOOL(0),
        wintypes.DWORD(exstyle),
    )
    if not ok:
        raise OSError("AdjustWindowRectEx 失败")
    return rect.left, rect.top, rect.right, rect.bottom


def force_client_size(
    hwnd: int,
    target_w: int,
    target_h: int,
    retries: int = 12,
) -> tuple[bool, int, int]:
    """
    保持当前客户区左上角在屏幕上的位置，将客户区设为 target_w x target_h。
    返回 (是否成功, 实际客户区宽, 高)。
    """
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    SWP_NOZORDER = 0x0004
    SWP_SHOWWINDOW = 0x0040

    for _ in range(retries):
        style = win32gui.GetWindowLong(hwnd, GWL_STYLE)
        exstyle = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
        # 客户区 (0,0)-(w,h) → 外框矩形
        ol, ot, or_, ob = _adjust_window_rect_ex(target_w, target_h, style, exstyle)
        outer_w = or_ - ol
        outer_h = ob - ot

        sx, sy = win32gui.ClientToScreen(hwnd, (0, 0))
        new_x = sx + ol
        new_y = sy + ot

        win32gui.SetWindowPos(
            hwnd,
            0,
            new_x,
            new_y,
            outer_w,
            outer_h,
            SWP_NOZORDER | SWP_SHOWWINDOW,
        )
        time.sleep(0.06)

        cw, ch = _get_client_size(hwnd)
        if cw == target_w and ch == target_h:
            return True, cw, ch

    cw, ch = _get_client_size(hwnd)
    return False, cw, ch


def main() -> None:
    p = argparse.ArgumentParser(description="将 GF2 窗口客户区强制为指定宽高")
    p.add_argument(
        "-W",
        "--width",
        type=int,
        default=DEFAULT_FORCE_CLIENT_W,
        help=f"客户区宽度（默认 {DEFAULT_FORCE_CLIENT_W}）",
    )
    p.add_argument(
        "-H",
        "--height",
        type=int,
        default=DEFAULT_FORCE_CLIENT_H,
        help=f"客户区高度（默认 {DEFAULT_FORCE_CLIENT_H}）",
    )
    args = p.parse_args()

    hwnd = find_game_hwnd()
    if not hwnd:
        print(
            "未找到游戏窗口（标题需包含以下关键字之一）："
            + ", ".join(WINDOW_TITLE_KEYWORDS),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.05)

    ok, cw, ch = force_client_size(hwnd, args.width, args.height)
    if ok:
        print(f"成功：客户区 = {cw}×{ch}")
    else:
        print(f"未能达到目标：当前客户区 = {cw}×{ch}（目标 {args.width}×{args.height}）")
        sys.exit(1)


if __name__ == "__main__":
    main()
