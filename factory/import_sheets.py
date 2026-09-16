#!/usr/bin/env python3
"""批量把 source/sheets/<英文>/<英文>_<状态>_NN.png 拆成单件入库。名称/状态对照表在此文件，新食材先加表。
用法: python3 factory/import_sheets.py [source/sheets]
"""
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = {"avocado": "牛油果", "cabbage": "卷心菜", "carrot": "胡萝卜", "corn": "玉米", "crab": "蟹肉",
         "cucumber": "黄瓜", "eggplant": "茄子", "mushroom": "蘑菇", "onion": "洋葱", "pepper": "红椒",
         "potato": "土豆", "tomato": "番茄", "zucchini": "西葫芦"}
STATES = {"raw": "生", "chopped": "切块", "roasted": "烤", "grilled": "炙烤", "sauteed": "炒"}
PAT = re.compile(r"^([a-z]+)_([a-z]+)_(\d+)\.png$")


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "source/sheets")
    skipped = []
    for p in sorted(src.rglob("*.png")):
        m = PAT.match(p.name)
        if not m or m.group(1) not in NAMES or m.group(2) not in STATES:
            skipped.append(p.name); continue
        r = subprocess.run([sys.executable, str(ROOT / "factory/split_sheet.py"), str(p),
                            "--name", NAMES[m.group(1)], "--state", STATES[m.group(2)]], capture_output=True, text=True)
        last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:]
        print(f"{p.name:32} → {NAMES[m.group(1)]}_{STATES[m.group(2)]}  {last}")
    for s in skipped: print("  跳过（不在对照表）:", s)


if __name__ == "__main__":
    main()
