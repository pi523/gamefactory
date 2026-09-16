#!/usr/bin/env python3
"""素材校验 + 生成 assets/manifest.json。规则见 specs/asset-naming.md。
用法: python3 factory/check_assets.py [assets]
"""
import json, re, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = {"食物", "道具", "场景", "UI"}
NAME_RE = re.compile(r"^([一-龥A-Za-z]+)(?:_([一-龥A-Za-z]+))?(\d+)\.png$")


def check_png(p: Path):
    probs = []
    im = Image.open(p)
    if im.mode != "RGBA":
        probs.append(f"mode={im.mode}，要求 RGBA"); return probs
    w, h = im.size
    if w != h: probs.append(f"非正方形 {w}x{h}")
    if not 512 <= w <= 2048: probs.append(f"边长 {w} 不在 512–2048")
    a = im.getchannel("A")
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if a.getpixel(xy) != 0: probs.append(f"角点 {xy} 不透明"); break
    bbox = a.point(lambda v: 255 if v > 16 else 0).getbbox()
    if not bbox:
        probs.append("全透明"); return probs
    occ = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / w
    if not 0.40 <= occ <= 0.95: probs.append(f"主体占比 {occ:.2f} 不在 0.40–0.95")
    # 白边检测：半透明边缘像素里接近纯白的比例
    px = im.load(); edge = white = 0
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            r, g, b, al = px[x, y]
            if 0 < al < 255:
                edge += 1
                if r > 245 and g > 245 and b > 245: white += 1
    if edge and white / edge > 0.5: probs.append(f"疑似白边（边缘 {white/edge:.0%} 近白）")
    return probs


def main():
    assets = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "assets").resolve()
    manifest, fails = {}, []
    for cat_dir in sorted(p for p in assets.iterdir() if p.is_dir()):
        if cat_dir.name not in CATEGORIES:
            fails.append(f"未知类别目录 {cat_dir.name}"); continue
        groups = {}
        for f in sorted(cat_dir.iterdir()):
            if f.name.startswith(".") or f.is_dir() or f.suffix.lower() != ".png": continue
            m = NAME_RE.match(f.name)
            if not m:
                fails.append(f"{cat_dir.name}/{f.name} 命名不合规（要求 名称+序号.png）"); continue
            name, state, idx = m.group(1), m.group(2) or "默认", int(m.group(3))
            groups.setdefault((name, state), []).append((idx, f))
            for pr in check_png(f): fails.append(f"{cat_dir.name}/{f.name}: {pr}")
        for (name, state), items in groups.items():
            idxs = sorted(i for i, _ in items)
            if idxs != list(range(1, len(idxs) + 1)):
                fails.append(f"{cat_dir.name}/{name}_{state} 序号不连续: {idxs}")
            manifest.setdefault(cat_dir.name, {}).setdefault(name, {})[state] = [f"assets/{cat_dir.name}/{f.name}" for _, f in sorted(items)]
    (assets / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(v) for c in manifest.values() for s in c.values() for v in s.values())
    print(f"manifest: {n} 个文件，{sum(len(c) for c in manifest.values())} 个物件，{sum(len(s) for c in manifest.values() for s in c.values())} 个物件×状态")
    for f in fails: print("  ✗", f)
    print(f"ASSETS: {'PASS' if not fails else 'FAIL'}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
