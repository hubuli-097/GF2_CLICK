import csv
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from pynput import mouse
import msvcrt


POINT_NAMES = [
    "锚点1",
    "坚果1",
    "补充坚果1",
    "水果1",
    "补充水果1",
    "水果2",
    "补充水果2",
    "水果3",
    "补充水果3",
    "水果4",
    "补充水果4",
    "小食1",
    "小食2",
    "小食3",
    "温度1",
    "温度2",
    "水1",
    "饮料1",
    "补充饮料1",
    "饮料2",
    "补充饮料2",
    "饮料3",
    "补充饮料3",
    "浮沫1",
    "浮沫2",
    "咖啡1",
    "补充咖啡1",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "calib")
JSON_PATH = os.path.join(OUT_DIR, "points.json")
CSV_PATH = os.path.join(OUT_DIR, "points.csv")
LOCK_PATH = os.path.join(OUT_DIR, ".capture_points.lock")
RUN_ID: Optional[str] = None


@dataclass
class PointRecord:
    name: str
    abs_x: int
    abs_y: int
    rel_dx: Optional[int]
    rel_dy: Optional[int]
    captured_at: str


def ensure_out_dir() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)


def acquire_single_instance_lock():
    """
    防止多个标定脚本同时运行，导致 points.json/points.csv 被不同进程交替覆盖写入。
    Windows 下用 msvcrt 文件锁实现单实例。
    """
    f = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        try:
            f.close()
        except OSError:
            pass
        print("检测到已有一个点位标定脚本正在运行。")
        print("请先关闭其它正在运行的标定窗口/终端，再重新启动本脚本。")
        sys.exit(2)
    return f


def write_json(anchor: Optional[PointRecord], points: list[PointRecord]) -> None:
    payload = {
        "anchor": asdict(anchor) if anchor else None,
        "points": [asdict(p) for p in points],
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "pid": os.getpid(),
            "run_id": RUN_ID,
            "note": "rel_dx/rel_dy 是相对于锚点1 (abs) 的偏移",
        },
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_csv(anchor: Optional[PointRecord], points: list[PointRecord]) -> None:
    header = ["name", "abs_x", "abs_y", "rel_dx", "rel_dy", "captured_at"]
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        if anchor:
            w.writerow([anchor.name, anchor.abs_x, anchor.abs_y, "", "", anchor.captured_at])
        for p in points:
            w.writerow([p.name, p.abs_x, p.abs_y, p.rel_dx, p.rel_dy, p.captured_at])


def main() -> None:
    ensure_out_dir()
    lock_handle = acquire_single_instance_lock()

    global RUN_ID
    RUN_ID = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"

    print(f"脚本路径：{os.path.abspath(__file__)}")
    print("输出文件：")
    print(f"- JSON: {JSON_PATH}")
    print(f"- CSV : {CSV_PATH}")
    print(f"本次会话：run_id={RUN_ID}")

    # 每次启动都清空上次输出，确保重新捕捉
    for p in (JSON_PATH, CSV_PATH):
        try:
            # 用覆盖写空的方式更稳（避免某些场景下编辑器/杀软锁文件导致删不掉）
            with open(p, "w", encoding="utf-8") as _:
                pass
            print(f"已清空：{p}")
        except OSError:
            # 如果文件被占用/无权限，后续写入时会覆盖或再次失败并抛错
            print(f"清空失败（可能被占用/无权限）：{p}")

    # 立即写入空骨架，避免“只启动未点击时文件仍显示旧内容/未刷新”的错觉
    write_json(None, [])
    write_csv(None, [])

    anchor: Optional[PointRecord] = None
    points: list[PointRecord] = []
    idx = 0
    lockout_until = 0.0

    def prompt_next() -> None:
        nonlocal idx
        if idx >= len(POINT_NAMES):
            print("已全部采集完成。结果已写入：")
            print(f"- {os.path.abspath(JSON_PATH)}")
            print(f"- {os.path.abspath(CSV_PATH)}")
            return
        print(f"下一项：{POINT_NAMES[idx]}（右键单击要记录的位置）")

    def on_click(x, y, button, pressed):
        nonlocal anchor, points, idx, lockout_until

        if not pressed:
            return
        if button != mouse.Button.right:
            return
        now = time.time()
        if now < lockout_until:
            return
        lockout_until = now + 0.15  # 防抖：避免一次点击触发多次

        if idx >= len(POINT_NAMES):
            return False  # stop listener

        name = POINT_NAMES[idx]
        ax = int(x)
        ay = int(y)
        ts = datetime.now().isoformat(timespec="seconds")

        if idx == 0:
            anchor = PointRecord(
                name=name,
                abs_x=ax,
                abs_y=ay,
                rel_dx=None,
                rel_dy=None,
                captured_at=ts,
            )
            print(f"已记录 {name}: abs=({ax},{ay})")
        else:
            if not anchor:
                print("错误：锚点1 未记录。请先记录锚点1。")
                return
            rec = PointRecord(
                name=name,
                abs_x=ax,
                abs_y=ay,
                rel_dx=ax - anchor.abs_x,
                rel_dy=ay - anchor.abs_y,
                captured_at=ts,
            )
            points.append(rec)
            print(f"已记录 {name}: abs=({ax},{ay}) rel=({rec.rel_dx},{rec.rel_dy})")

        write_json(anchor, points)
        write_csv(anchor, points)
        idx += 1
        prompt_next()

        if idx >= len(POINT_NAMES):
            return False  # stop listener

    print("点位标定模式已启动。")
    print("说明：第 1 个点位是锚点1（绝对坐标）；后续点位会记录相对锚点1的 dx/dy。")
    print("操作：对每一项，用鼠标右键单击目标位置。退出：Ctrl+C。")
    prompt_next()

    listener = mouse.Listener(on_click=on_click)
    listener.start()
    try:
        listener.join()
    except KeyboardInterrupt:
        listener.stop()
        print("已退出。当前进度已保存到：")
        print(f"- {os.path.abspath(JSON_PATH)}")
        print(f"- {os.path.abspath(CSV_PATH)}")
    finally:
        try:
            # 释放锁
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            lock_handle.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()

