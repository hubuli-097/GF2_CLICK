# -*- coding: utf-8 -*-
"""
GF2 自动点击助手 - GUI 版本
双击运行或通过 PyInstaller 打包的 exe 启动。
需以管理员身份运行方可点击以管理员运行的游戏窗口。
"""
from __future__ import annotations

import ctypes
import sys
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, font as tkfont
# 导入核心逻辑（确保在项目根目录或已安装）
try:
    from gf2_bot import run_bot
    from force_client_window import (
        DEFAULT_FORCE_CLIENT_H,
        DEFAULT_FORCE_CLIENT_W,
        find_game_hwnd,
        force_client_size,
    )
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from gf2_bot import run_bot
    from force_client_window import (
        DEFAULT_FORCE_CLIENT_H,
        DEFAULT_FORCE_CLIENT_W,
        find_game_hwnd,
        force_client_size,
    )


class GF2ClickApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("GF2 自动点击助手")
        self.root.geometry("520x420")
        self.root.resizable(True, True)
        self.root.minsize(400, 320)

        self.stop_event = threading.Event()
        self.bot_thread: threading.Thread | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.is_running = False

        self._build_ui()
        self._bind_hotkeys()
        self._start_log_poll()

    def _build_ui(self) -> None:
        # 标题
        title_frame = tk.Frame(self.root, padx=10, pady=8)
        title_frame.pack(fill=tk.X)
        title_font = tkfont.Font(size=14, weight="bold")
        tk.Label(title_frame, text="GF2 自动点击助手", font=title_font).pack(side=tk.LEFT)

        # 按钮区
        btn_frame = tk.Frame(self.root, padx=10, pady=5)
        btn_frame.pack(fill=tk.X)
        self.btn_start = tk.Button(
            btn_frame,
            text="启动",
            command=self._on_start,
            width=8,
            height=1,
            bg="#4CAF50",
            fg="white",
            font=("", 10),
            cursor="hand2",
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_stop = tk.Button(
            btn_frame,
            text="停止",
            command=self._on_stop,
            width=8,
            height=1,
            bg="#f44336",
            fg="white",
            font=("", 10),
            state=tk.DISABLED,
            cursor="hand2",
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_force_window = tk.Button(
            btn_frame,
            text="对齐客户区",
            command=self._on_force_window,
            width=10,
            height=1,
            bg="#2196F3",
            fg="white",
            font=("", 10),
            cursor="hand2",
        )
        self.btn_force_window.pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="状态: 就绪")
        tk.Label(btn_frame, textvariable=self.status_var, fg="#666").pack(side=tk.LEFT, padx=(20, 0))
        tk.Label(btn_frame, text="  (F10启动 F12停止)", fg="#999", font=("", 8)).pack(side=tk.LEFT)
        tk.Label(
            btn_frame,
            text=f"  对齐={DEFAULT_FORCE_CLIENT_W}×{DEFAULT_FORCE_CLIENT_H}",
            fg="#999",
            font=("", 8),
        ).pack(side=tk.LEFT)

        # 锚点修正：x 往右移，y 往上移（像素）
        opt_frame = tk.Frame(self.root, padx=10, pady=4)
        opt_frame.pack(fill=tk.X)
        tk.Label(opt_frame, text="锚点修正 x:", fg="#666").pack(side=tk.LEFT, padx=(0, 2))
        self.anchor_offset_x_var = tk.StringVar(value="25")
        self.anchor_offset_x_entry = tk.Entry(opt_frame, textvariable=self.anchor_offset_x_var, width=5)
        self.anchor_offset_x_entry.pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(opt_frame, text="y:", fg="#666").pack(side=tk.LEFT, padx=(0, 2))
        self.anchor_offset_y_var = tk.StringVar(value="25")
        self.anchor_offset_y_entry = tk.Entry(opt_frame, textvariable=self.anchor_offset_y_var, width=5)
        self.anchor_offset_y_entry.pack(side=tk.LEFT)
        tk.Label(opt_frame, text="  (正数=往右/上移，默认 x:25 y:25)", fg="#999", font=("", 8)).pack(side=tk.LEFT, padx=(8, 0))

        # 日志区
        log_label = tk.Label(self.root, text="运行日志:", anchor=tk.W)
        log_label.pack(fill=tk.X, padx=10, pady=(10, 2))
        self.log_text = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            height=16,
            font=("Consolas", 9),
            state=tk.DISABLED,
            bg="#f8f8f8",
            fg="#333",
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def _log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _bind_hotkeys(self) -> None:
        """F10 启动，F12 停止（全局热键）"""
        try:
            from pynput import keyboard
            def on_f10():
                self.root.after(0, self._on_start)
            def on_f12():
                self.root.after(0, self._on_stop)
            self._hotkey_listener = keyboard.GlobalHotKeys({
                "<f10>": on_f10,
                "<f12>": on_f12,
            })
            self._hotkey_listener.start()
        except Exception:
            self._hotkey_listener = None

    def _get_anchor_offset(self) -> tuple[int, int]:
        try:
            x = int(self.anchor_offset_x_var.get().strip() or "0")
        except ValueError:
            x = 0
        try:
            y = int(self.anchor_offset_y_var.get().strip() or "0")
        except ValueError:
            y = 0
        return (x, y)

    def _on_force_window(self) -> None:
        """将游戏窗口客户区强制为标定尺寸（与 force_client_window 默认一致）。"""
        self.btn_force_window.config(state=tk.DISABLED)

        def worker() -> None:
            try:
                import win32gui
            except ImportError:
                self.root.after(
                    0,
                    lambda: self._log("对齐客户区失败: 请先 pip install pywin32"),
                )
                self.root.after(0, lambda: self.btn_force_window.config(state=tk.NORMAL))
                return
            hwnd = find_game_hwnd()
            if not hwnd:
                self.root.after(
                    0,
                    lambda: self._log("对齐客户区: 未找到游戏窗口，请先打开游戏。"),
                )
                self.root.after(0, lambda: self.btn_force_window.config(state=tk.NORMAL))
                return
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            import time as _time

            _time.sleep(0.05)
            ok, cw, ch = force_client_size(
                hwnd, DEFAULT_FORCE_CLIENT_W, DEFAULT_FORCE_CLIENT_H
            )
            tw, th = DEFAULT_FORCE_CLIENT_W, DEFAULT_FORCE_CLIENT_H

            def done() -> None:
                self.btn_force_window.config(state=tk.NORMAL)
                if ok:
                    self._log(f"对齐客户区: 成功，客户区 {cw}×{ch}")
                else:
                    self._log(
                        f"对齐客户区: 未完全达标，当前 {cw}×{ch}（目标 {tw}×{th}）"
                    )

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.stop_event.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.anchor_offset_x_entry.config(state=tk.DISABLED)
        self.anchor_offset_y_entry.config(state=tk.DISABLED)
        self.status_var.set("状态: 运行中")

        anchor_offset_x, anchor_offset_y = self._get_anchor_offset()

        def worker() -> None:
            try:
                run_bot(
                    stop_event=self.stop_event,
                    log=self._log,
                    anchor_offset=(anchor_offset_x, anchor_offset_y),
                )
            except Exception as e:
                self._log(f"运行失败: {e}")
            finally:
                self.root.after(0, self._on_stopped)

        self.bot_thread = threading.Thread(target=worker, daemon=True)
        self.bot_thread.start()

    def _on_stop(self) -> None:
        if not self.is_running:
            return
        self.stop_event.set()
        self.status_var.set("状态: 正在停止...")
        self.btn_stop.config(state=tk.DISABLED)

    def _on_stopped(self) -> None:
        self.is_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.anchor_offset_x_entry.config(state=tk.NORMAL)
        self.anchor_offset_y_entry.config(state=tk.NORMAL)
        self.status_var.set("状态: 已停止")

    def _start_log_poll(self) -> None:
        def poll() -> None:
            try:
                while True:
                    msg = self.log_queue.get_nowait()
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, msg + "\n")
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
            except queue.Empty:
                pass
            self.root.after(80, poll)

        self.root.after(80, poll)

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        if self.is_running:
            self._on_stop()
            self.root.after(500, self._do_close)
        else:
            self._do_close()

    def _do_close(self) -> None:
        if getattr(self, "_hotkey_listener", None):
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
        if self.is_running:
            self.stop_event.set()
            if self.bot_thread and self.bot_thread.is_alive():
                self.bot_thread.join(timeout=2)
        self.root.destroy()


def main() -> None:
    app = GF2ClickApp()
    app.run()


def _request_admin_and_rerun() -> bool:
    """若当前非管理员，请求提升后重新启动；返回 True 表示已重新启动，调用者应退出。"""
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return False
    except Exception:
        return False
    # 以管理员身份重新启动
    if getattr(sys, "frozen", False):
        params = ""
    else:
        params = " ".join(f'"{a}"' if " " in a else a for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )
    return True


if __name__ == "__main__":
    if _request_admin_and_rerun():
        sys.exit(0)
    main()
