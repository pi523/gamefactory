#!/usr/bin/env python3
"""给人复核用：把 manifest 里每个 物件×状态 的前 N 件拼成一张缩略图。
用法: python3 factory/contact_sheet.py [--n 6] [--out reports/contact.png] [--full 蘑菇_生]（--full 输出该组全部件）
"""
import argparse, json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=6); ap.add_argument("--out", default=str(ROOT / "reports/contact.png"))
    ap.add_argument("--full", default=None); ap.add_argument("--thumb", type=int, default=110)
    a = ap.parse_args(); S = a.thumb
    m = json.loads((ROOT / "assets/manifest.json").read_text(encoding="utf-8"))
    groups = [(f"{n}_{s}", fs) for cat in m.values() for n, st in cat.items() for s, fs in st.items()]
    if a.full:
        fs = dict(groups)[a.full]; cols = 6; rows = (len(fs) + cols - 1) // cols
        im = Image.new("RGB", (S * cols, S * rows), (40, 40, 40))
        for i, f in enumerate(fs):
            t = Image.open(ROOT / f).convert("RGBA").resize((S, S)); im.paste(t, ((i % cols) * S, (i // cols) * S), t)
    else:
        im = Image.new("RGB", (S * a.n + 200, S * len(groups)), (40, 40, 40)); d = ImageDraw.Draw(im)
        for r, (label, fs) in enumerate(groups):
            d.text((8, r * S + S // 2 - 6), f"{label} ({len(fs)})", fill=(255, 255, 255))
            for c, f in enumerate(fs[: a.n]):
                t = Image.open(ROOT / f).convert("RGBA").resize((S, S)); im.paste(t, (200 + c * S, r * S), t)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); im.save(a.out); print("→", a.out)


if __name__ == "__main__":
    main()
