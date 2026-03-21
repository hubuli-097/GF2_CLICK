# -*- coding: utf-8 -*-
"""
读取当前「游戏窗口客户区」的实际像素尺寸（与 gf2_bot / force_client_window 同一套窗口匹配规则）。

用于：游戏内显示 1600×900 时，核对 Windows 侧 GetClientRect 是否略大/略小，
便于之后改标定分辨率或 force_client_window 的目标宽高。

依赖：pip install pywin32

用法：
    python capture_client_resolution.py              # 打印一次
    python capture_client_resolution.py --watch      # 每 1 秒刷新（可调 --interval）
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from datetime import datetime

try:
    import win32gui
except ImportError:
    print("请先安装: pip install pywin32", file=sys.stderr)
    sys.exit(1)

from force_client_window import find_game_hwnd


def _dpi_for_window(hwnd: int) -> int | None:
    user32 = ctypes.windll.user32
    if not hasattr(user32, "GetDpiForWindow"):
        return None
    try:
        return int(user32.GetDpiForWindow(hwnd))
    except Exception:
        return None


def measure(hwnd: int) -> dict[str, int | str]:
    title = win32gui.GetWindowText(hwnd) or ""
    cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
    cw, ch = cr - cl, cb - ct
    wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
    ow, oh = wr - wl, wb - wt
    dpi = _dpi_for_window(hwnd)
    return {
        "title": title,
        "client_w": cw,
        "client_h": ch,
        "outer_w": ow,
        "outer_h": oh,
        "dpi": dpi if dpi is not None else -1,
    }


def _format_line(m: dict[str, int | str]) -> str:
    dpi = m["dpi"]
    dpi_s = f"{dpi}" if dpi != -1 else "n/a"
    return (
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"客户区: {m['client_w']}×{m['client_h']} px  |  "
        f"外框: {m['outer_w']}×{m['outer_h']} px  |  "
        f"DPI: {dpi_s}  |  "
        f"标题: {m['title'][:60]}{'…' if len(str(m['title'])) > 60 else ''}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="捕捉游戏窗口当前客户区分辨率（像素）")
    p.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help="持续刷新（默认每 1 秒）",
    )
    p.add_argument(
        "-i",
        "--interval",
        type=float,
        default=1.0,
        help="watch 模式下刷新间隔（秒）",
    )
    args = p.parse_args()

    if args.watch:
        print("持续读取中，Ctrl+C 结束。请保持游戏窗口可见。\n")
        try:
            while True:
                hwnd = find_game_hwnd()
                if not hwnd:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] 未找到游戏窗口。",
                        flush=True,
                    )
                else:
                    print(_format_line(measure(hwnd)), flush=True)
                time.sleep(max(0.2, args.interval))
        except KeyboardInterrupt:
            print("\n已退出。")
            return

    hwnd = find_game_hwnd()
    if not hwnd:
        print("未找到游戏窗口（标题需与 gf2_bot.WINDOW_TITLE_KEYWORDS 匹配）。", file=sys.stderr)
        sys.exit(1)

    m = measure(hwnd)
    print(_format_line(m))
    print()
    print("说明：「客户区」即 GetClientRect 的宽高，与点击坐标所在画布一致。")
    print("若与游戏内显示分辨率不一致，以本脚本输出为准做标定或缩放。")


if __name__ == "__main__":
    main()
