# -*- coding: utf-8 -*-
"""
校验 click_shots 下模板图与 calib/points.json 的对应关系。

规则与 gf2_bot.load_templates 一致：图片文件名（不含扩展名）经 normalize 后
须等于 points.json 里某点位的 name。例如：
  click_shots/小食3.png  <->  points 中 name 为「小食3」的 abs_x/abs_y。

用法: python shot_point_mapping.py
      python shot_point_mapping.py 小食3   # 只检查某一名字
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


CALIB_PATH = _base_dir() / "calib" / "points.json"
TEMPLATE_DIR = _base_dir() / "click_shots"

# 显式登记：模板文件 -> 与 bot 使用相同的点位名（便于文档与人工核对）
EXPLICIT_SHOTS: dict[str, str] = {
    "小食3.png": "小食3",
    "水果4.png": "水果4",
}


def normalize_name(name: str) -> str:
    return (
        name.replace("（", "(")
        .replace("）", ")")
        .replace(" ", "")
        .replace("_", "")
        .strip()
    )


def load_points_by_name() -> dict[str, dict]:
    raw = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    anchor = raw.get("anchor")
    if anchor and anchor.get("name"):
        out[str(anchor["name"])] = anchor
    for p in raw.get("points", []):
        out[str(p["name"])] = p
    return out


def main() -> None:
    filter_name: str | None = None
    if len(sys.argv) >= 2:
        filter_name = normalize_name(sys.argv[1])

    if not CALIB_PATH.is_file():
        print(f"未找到: {CALIB_PATH}")
        sys.exit(1)
    if not TEMPLATE_DIR.is_dir():
        print(f"未找到目录: {TEMPLATE_DIR}")
        sys.exit(1)

    points = load_points_by_name()

    # 核对 EXPLICIT_SHOTS 与磁盘、JSON
    for fname, pname in EXPLICIT_SHOTS.items():
        path = TEMPLATE_DIR / fname
        if not path.is_file():
            print(f"[错误] 显式对应缺少文件: {path}")
            continue
        rec = points.get(pname)
        if not rec:
            print(f"[错误] 显式对应 JSON 无点位「{pname}」")
            continue
        print(
            f"[显式] {fname}  ->  「{pname}」  "
            f"abs=({rec['abs_x']},{rec['abs_y']})  "
            f"rel=({rec.get('rel_dx','?')},{rec.get('rel_dy','?')})"
        )

    # 扫描全部图片，与 JSON 对齐
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    for path in sorted(TEMPLATE_DIR.iterdir()):
        if path.suffix.lower() not in exts:
            continue
        stem = normalize_name(path.stem)
        if filter_name and stem != filter_name:
            continue
        rec = points.get(stem)
        if not rec:
            print(f"[孤立模板] {path.name}  ->  stem「{stem}」在 points.json 中无同名点位")
            continue
        tag = "OK"
        if path.name in EXPLICIT_SHOTS:
            if EXPLICIT_SHOTS[path.name] != stem:
                tag = "WARN:EXPLICIT_MISMATCH"
        print(
            f"[{tag}] {path.name}  ->  「{stem}」  "
            f"abs=({rec['abs_x']},{rec['abs_y']})"
        )

    if filter_name:
        # 若只查一名，再提示是否缺图
        if filter_name not in points:
            print(f"[错误] JSON 中无点位「{filter_name}」")
        else:
            hit = False
            for path in TEMPLATE_DIR.iterdir():
                if path.suffix.lower() not in exts:
                    continue
                if normalize_name(path.stem) == filter_name:
                    hit = True
                    break
            if not hit:
                print(f"[错误] 无模板图对应「{filter_name}」（需在 {TEMPLATE_DIR} 下放同名图）")


if __name__ == "__main__":
    main()
