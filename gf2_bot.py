import ctypes
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np
from pynput.mouse import Button, Controller

# PyInstaller 打包后资源在临时目录
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

CALIB_PATH = BASE_DIR / "calib" / "points.json"
TEMPLATE_DIR = BASE_DIR / "click_shots"

# 只处理这批主要点位（不含补充*，且先忽略小食3）
ACTIVE_POINT_NAMES = {
    "坚果1",
    "水果1",
    "水果2",
    "水果3",
    "小食1",
    "小食2",
    "温度1",
    "温度2",
    "水1",
    "饮料1",
    "饮料2",
    "饮料3",
    "浮沫1",
    "咖啡1",
    "锚点1",
}

# 命中主按钮后，自动补充一次
AUTO_REPLENISH = {
    "坚果1": "补充坚果1",
    "水果1": "补充水果1",
    "水果2": "补充水果2",
    "水果3": "补充水果3",
    "饮料1": "补充饮料1",
    "饮料2": "补充饮料2",
    "饮料3": "补充饮料3",
    "咖啡1": "补充咖啡1",
}

MATCH_THRESHOLD = 0.85
ANCHOR_MATCH_THRESHOLD = 0.55
LOOP_SLEEP_SEC = 0.08
MIN_CLICK_INTERVAL_SEC = 1.0
USE_WINDOW_TOPLEFT_AS_ANCHOR = True
SUBMIT_IDLE_SEC = 1.0
SUBMIT_TEMPLATE_NAME = "提交1"
SUBMIT_MATCH_THRESHOLD = 0.78
SUBMIT_POST_WAIT_SEC = 1.0

# 仅在右上角订单区域识别（固定 380x200，以进程窗口右上角为原点）
ROI_WIDTH = 380
ROI_HEIGHT = 200

# 通过窗口标题关键字锁定游戏窗口（进程捕获的实用替代）
WINDOW_TITLE_KEYWORDS = ["少女前线2", "GF2_Exilium"]

# 坐标缩放：标定时的 DPI 缩放 / 运行时的 DPI 缩放。标定 150%、运行 100% 时填 1.5；相同则填 1.0
COORD_SCALE = 1.0

# 对局部截图或易变图标可单独放宽阈值
PER_TEMPLATE_THRESHOLD = {
    "温度1": 0.70,
}


@dataclass
class CaptureArea:
    left: int
    top: int
    width: int
    height: int


@dataclass
class Point:
    name: str
    abs_x: int
    abs_y: int


@dataclass
class Template:
    point_name: str
    path: Path
    gray: np.ndarray
    width: int
    height: int


def normalize_name(name: str) -> str:
    # 统一全角/半角括号、空格，增强文件名与点位名匹配容错
    return (
        name.replace("（", "(")
        .replace("）", ")")
        .replace(" ", "")
        .replace("_", "")
        .strip()
    )


def load_calib_points() -> Dict[str, Point]:
    if not CALIB_PATH.exists():
        raise FileNotFoundError(f"未找到坐标文件: {CALIB_PATH}")
    data = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
    points: Dict[str, Point] = {}

    anchor = data.get("anchor")
    if anchor:
        points[anchor["name"]] = Point(
            anchor["name"], int(anchor["abs_x"]), int(anchor["abs_y"])
        )
    for p in data.get("points", []):
        points[p["name"]] = Point(p["name"], int(p["abs_x"]), int(p["abs_y"]))
    return points


def load_templates() -> List[Template]:
    if not TEMPLATE_DIR.exists():
        raise FileNotFoundError(f"未找到模板目录: {TEMPLATE_DIR}")

    templates: List[Template] = []
    for path in sorted(TEMPLATE_DIR.glob("*")):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            continue
        img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue

        point_name = normalize_name(path.stem)
        templates.append(
            Template(
                point_name=point_name,
                path=path,
                gray=img,
                width=img.shape[1],
                height=img.shape[0],
            )
        )
    return templates


def find_best_match(
    frame_gray: np.ndarray, tpl_gray: np.ndarray
) -> Tuple[float, Tuple[int, int]]:
    result = cv2.matchTemplate(frame_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return float(max_val), (int(max_loc[0]), int(max_loc[1]))


def find_multi_matches(
    frame_gray: np.ndarray,
    tpl_gray: np.ndarray,
    threshold: float,
) -> List[Tuple[int, int, float]]:
    """
    返回模板在 ROI 中的多个匹配点 (x, y, score)，并做简单去重，支持同一产品同屏出现多次。
    """
    result = cv2.matchTemplate(frame_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= threshold)
    if len(xs) == 0:
        return []

    raw: List[Tuple[int, int, float]] = []
    for x, y in zip(xs.tolist(), ys.tolist()):
        raw.append((int(x), int(y), float(result[y, x])))

    # 分数高优先，做空间去重（防止同一图标周围出现密集重复点）
    raw.sort(key=lambda it: it[2], reverse=True)
    selected: List[Tuple[int, int, float]] = []
    min_dx = max(8, tpl_gray.shape[1] // 2)
    min_dy = max(8, tpl_gray.shape[0] // 2)
    for x, y, s in raw:
        too_close = False
        for sx, sy, _ in selected:
            if abs(x - sx) < min_dx and abs(y - sy) < min_dy:
                too_close = True
                break
        if not too_close:
            selected.append((x, y, s))

    return selected


def find_best_match_robust(
    frame_gray: np.ndarray, tpl_gray: np.ndarray
) -> Tuple[float, Tuple[int, int], str]:
    # 策略1：原灰度匹配
    score_gray, loc_gray = find_best_match(frame_gray, tpl_gray)
    best_score = score_gray
    best_loc = loc_gray
    best_mode = "gray"

    # 策略2：边缘匹配（对亮度变化更稳）
    edge_frame = cv2.Canny(frame_gray, 50, 150)
    edge_tpl = cv2.Canny(tpl_gray, 50, 150)
    score_edge, loc_edge = find_best_match(edge_frame, edge_tpl)
    if score_edge > best_score:
        best_score = score_edge
        best_loc = loc_edge
        best_mode = "edge"

    return best_score, best_loc, best_mode


def get_roi_rect(frame_gray: np.ndarray) -> Tuple[int, int, int, int]:
    h, w = frame_gray.shape[:2]
    roi_w = min(ROI_WIDTH, w)
    roi_h = min(ROI_HEIGHT, h)
    x1 = max(0, w - roi_w)  # 右上角
    y1 = 0
    return x1, y1, roi_w, roi_h


def find_game_window_rect() -> Optional[CaptureArea]:
    user32 = ctypes.windll.user32
    title_hits: List[Tuple[int, int]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetWindowTextW = user32.GetWindowTextW
    IsWindowVisible = user32.IsWindowVisible
    GetClientRect = user32.GetClientRect
    ClientToScreen = user32.ClientToScreen

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def callback(hwnd, lparam):
        if not IsWindowVisible(hwnd):
            return True
        length = GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        low_title = title.lower()
        if any(k.lower() in low_title for k in WINDOW_TITLE_KEYWORDS):
            rect = RECT()
            if not GetClientRect(hwnd, ctypes.byref(rect)):
                return True
            w = int(rect.right - rect.left)
            h = int(rect.bottom - rect.top)
            if w <= 0 or h <= 0:
                return True
            pt = POINT(0, 0)
            if not ClientToScreen(hwnd, ctypes.byref(pt)):
                return True
            area = CaptureArea(left=int(pt.x), top=int(pt.y), width=w, height=h)
            # 优先更大的可见客户区窗口
            title_hits.append((w * h, len(title)))
            setattr(find_game_window_rect, "_best_area", area)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return getattr(find_game_window_rect, "_best_area", None) if title_hits else None


def grab_screen_gray(
    sct: mss.mss, area: Optional[CaptureArea]
) -> Tuple[np.ndarray, int, int]:
    if area is None:
        mon = sct.monitors[0]  # 虚拟屏幕（多显示器）
        left = int(mon["left"])
        top = int(mon["top"])
        width = int(mon["width"])
        height = int(mon["height"])
    else:
        left = area.left
        top = area.top
        width = area.width
        height = area.height

    raw = sct.grab(
        {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        }
    )
    frame = np.array(raw)[:, :, :3]  # BGRA -> BGR
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return gray, left, top


def click_at(mouse: Controller, x: int, y: int) -> None:
    mouse.position = (x, y)
    time.sleep(0.01)
    mouse.click(Button.left, 1)


def resolve_offset(
    frame_gray: np.ndarray,
    templates: List[Template],
    calib_points: Dict[str, Point],
    frame_left: int,
    frame_top: int,
    use_window_topleft_anchor: bool,
    log: Callable[[str], None],
) -> Tuple[int, int]:
    anchor_tpl = next((t for t in templates if t.point_name == "锚点1"), None)
    anchor_pt = calib_points.get("锚点1")
    if not anchor_pt:
        log("未找到锚点坐标，偏移按 0,0 处理。")
        return 0, 0

    if use_window_topleft_anchor:
        offset_x = frame_left - anchor_pt.abs_x
        offset_y = frame_top - anchor_pt.abs_y
        log(
            f"已启用窗口左上角锚点模式: window_left_top=({frame_left},{frame_top}), offset=({offset_x},{offset_y})"
        )
        return offset_x, offset_y

    if not anchor_tpl:
        log("未找到锚点模板或锚点坐标，偏移按 0,0 处理。")
        return 0, 0

    score, (ax, ay), mode = find_best_match_robust(frame_gray, anchor_tpl.gray)
    if score < ANCHOR_MATCH_THRESHOLD:
        log(f"锚点识别置信度不足({score:.3f}, mode={mode})，偏移按 0,0 处理。")
        return 0, 0

    # 若是窗口截图，模板坐标需转回全屏绝对坐标再和标定坐标做偏移
    abs_x = frame_left + ax
    abs_y = frame_top + ay
    offset_x = abs_x - anchor_pt.abs_x
    offset_y = abs_y - anchor_pt.abs_y
    log(
        f"锚点识别成功 score={score:.3f}, mode={mode}, anchor_abs=({abs_x},{abs_y}), offset=({offset_x},{offset_y})"
    )
    return offset_x, offset_y


def build_target_points(
    calib_points: Dict[str, Point],
    offset_x: int,
    offset_y: int,
    anchor_pt: Optional[Point],
    scale: float = 1.0,
    anchor_offset: Tuple[int, int] = (0, 0),
) -> Dict[str, Tuple[int, int]]:
    """相对窗口左上角等比例缩放，anchor_offset=(x,y) 表示整体往右x、往上y像素（正数）"""
    if anchor_pt is None:
        anchor_pt = Point("", 0, 0)
    adj_x, adj_y = anchor_offset  # adj_x=往右, adj_y=往上(屏幕y减小)
    targets: Dict[str, Tuple[int, int]] = {}
    frame_left = offset_x + anchor_pt.abs_x
    frame_top = offset_y + anchor_pt.abs_y
    for name, p in calib_points.items():
        rel_x = (p.abs_x - anchor_pt.abs_x) * scale
        rel_y = (p.abs_y - anchor_pt.abs_y) * scale
        targets[normalize_name(name)] = (
            int(frame_left + rel_x + adj_x),
            int(frame_top + rel_y - adj_y),
        )
    return targets


def run_bot(
    stop_event: "object",
    log: Callable[[str], None] = print,
    coord_scale: float | None = None,
    anchor_offset: Tuple[int, int] = (0, 0),
) -> None:
    """主循环，支持通过 stop_event 停止，log 用于输出日志。"""
    log("GF2 点击脚本启动中...")
    calib_points = load_calib_points()
    templates = load_templates()
    if not templates:
        raise RuntimeError(f"模板目录为空: {TEMPLATE_DIR}")

    log(f"已加载模板数量: {len(templates)}")
    log(f"模板目录: {TEMPLATE_DIR}")

    mouse = Controller()
    seen_active: Dict[str, bool] = {}
    last_click_time = 0.0

    def click_with_interval(x: int, y: int, why: str) -> None:
        nonlocal last_click_time
        now = time.time()
        wait_sec = MIN_CLICK_INTERVAL_SEC - (now - last_click_time)
        if wait_sec > 0:
            stop_event.wait(wait_sec)
        if stop_event.is_set():
            return
        click_at(mouse, x, y)
        last_click_time = time.time()
        log(f"{why} 点击({x},{y})")

    with mss.mss() as sct:
        area = find_game_window_rect()
        if area:
            log(
                f"已锁定游戏窗口客户区: left={area.left}, top={area.top}, w={area.width}, h={area.height}"
            )
        else:
            log("未锁定到游戏窗口，将回退到全屏截图识别。")

        first_frame, frame_left, frame_top = grab_screen_gray(sct, area)
        offset_x, offset_y = resolve_offset(
            first_frame,
            templates,
            calib_points,
            frame_left,
            frame_top,
            use_window_topleft_anchor=bool(area and USE_WINDOW_TOPLEFT_AS_ANCHOR),
            log=log,
        )
        anchor_pt = calib_points.get("锚点1")
        scale = coord_scale if coord_scale is not None else COORD_SCALE
        target_points = build_target_points(
            calib_points, offset_x, offset_y, anchor_pt, scale, anchor_offset
        )
        if scale != 1.0:
            log(f"已启用坐标缩放: COORD_SCALE={scale}")
        if anchor_offset != (0, 0):
            log(f"已启用锚点修正: x={anchor_offset[0]}, y={anchor_offset[1]}")

        active_templates = [
            t
            for t in templates
            if t.point_name in ACTIVE_POINT_NAMES
            and t.point_name in target_points
            and t.point_name != "锚点1"
        ]
        if not active_templates:
            raise RuntimeError("没有可用模板可执行。请检查模板文件名是否与点位名对应。")

        missing_points = [
            t.point_name for t in active_templates if t.point_name not in target_points
        ]
        if missing_points:
            log(
                "警告：以下模板无坐标，已跳过："
                + ", ".join(sorted(set(missing_points)))
            )

        roi_x, roi_y, roi_w, roi_h = get_roi_rect(first_frame)
        log(f"识别区域(右上): x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h}")

        submit_tpl = next(
            (
                t
                for t in templates
                if t.point_name == normalize_name(SUBMIT_TEMPLATE_NAME)
            ),
            None,
        )
        if submit_tpl is None:
            log(f"警告：未找到提交模板 {SUBMIT_TEMPLATE_NAME}，将跳过自动提交。")

        log("开始运行，点击 [停止] 可结束。")
        last_recognized_at = 0.0
        round_has_action = False

        while not stop_event.is_set():
            frame_gray, _, _ = grab_screen_gray(sct, area)
            roi = frame_gray[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]

            # 候选按“从左到右”选择，满足顺序要求。
            # 每帧最多执行一个动作（稳定优先）。
            # item: (mx, score, template, detect_key)
            candidates: List[Tuple[int, float, Template, str]] = []
            visible_keys: set[str] = set()

            for tpl in active_templates:
                threshold = PER_TEMPLATE_THRESHOLD.get(tpl.point_name, MATCH_THRESHOLD)
                matches = find_multi_matches(roi, tpl.gray, threshold)
                if not matches:
                    continue

                for mx, my, score in matches:
                    detect_key = f"{tpl.point_name}@x{mx}_y{my}"
                    visible_keys.add(detect_key)

                    # 已在“出现中”且触发过，本轮跳过，直到该位置消失
                    if seen_active.get(detect_key, False):
                        continue

                    # mx 是在 ROI 内的匹配左上角 x，用来做左->右排序
                    candidates.append((int(mx), float(score), tpl, detect_key))

            if candidates:
                # 先按 x 从小到大（左到右），同 x 再按分数高到低
                candidates.sort(key=lambda it: (it[0], -it[1]))
                _, best_score, best_tpl, best_key = candidates[0]
                name = best_tpl.point_name
                x, y = target_points[name]
                click_with_interval(
                    x, y, why=f"[命中] {name} score={best_score:.3f} ->"
                )
                seen_active[best_key] = True
                last_recognized_at = time.time()
                round_has_action = True

                replenish_name = AUTO_REPLENISH.get(name)
                if replenish_name:
                    rep_norm = normalize_name(replenish_name)
                    rep_xy = target_points.get(rep_norm)
                    if rep_xy:
                        click_with_interval(
                            rep_xy[0],
                            rep_xy[1],
                            why=f"        -> 自动补充 {replenish_name} ->",
                        )
                        last_recognized_at = time.time()
                    else:
                        print(f"        -> 缺少补充坐标: {replenish_name}")

            # 清理已消失的 key，让同一位置下次出现时可再次触发
            stale_keys = [k for k in seen_active.keys() if k not in visible_keys]
            for k in stale_keys:
                seen_active.pop(k, None)

            # 1s 无新识别 -> 尝试点击提交，进入下一轮
            if submit_tpl is not None and round_has_action:
                if time.time() - last_recognized_at >= SUBMIT_IDLE_SEC:
                    sub_score, (sx, sy) = find_best_match(frame_gray, submit_tpl.gray)
                    if sub_score >= SUBMIT_MATCH_THRESHOLD:
                        # 点击提交模板中心点（当前窗口截图坐标 -> 全屏绝对坐标）
                        abs_x = frame_left + sx + submit_tpl.width // 2
                        abs_y = frame_top + sy + submit_tpl.height // 2
                        click_with_interval(
                            abs_x,
                            abs_y,
                            why=f"[空闲{SUBMIT_IDLE_SEC:.1f}s] 自动提交 score={sub_score:.3f} ->",
                        )
                        # 提交后额外等待，避免游戏结算动画期间重复点击
                        stop_event.wait(SUBMIT_POST_WAIT_SEC)
                        round_has_action = False
                        last_recognized_at = time.time()
                        seen_active.clear()
                    else:
                        log(f"[自动提交] 未命中提交按钮，score={sub_score:.3f}")

            stop_event.wait(LOOP_SLEEP_SEC)

    log("已停止。")


def main() -> None:
    """命令行入口，使用 print 输出，Ctrl+C 可停止。"""
    import threading

    stop = threading.Event()

    def worker() -> None:
        try:
            run_bot(stop_event=stop, log=print)
        except Exception as e:
            print(f"运行失败: {e}")

    t = threading.Thread(target=worker, daemon=False)
    t.start()
    try:
        while t.is_alive():
            t.join(timeout=0.3)
    except KeyboardInterrupt:
        stop.set()
        print("正在停止...")
        t.join(timeout=3)
        print("已退出。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已退出。")
    except Exception as e:
        print(f"运行失败: {e}")
