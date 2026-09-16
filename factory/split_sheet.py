#!/usr/bin/env python3
"""把"一张图多物件"的透明底拼图表拆成单件，按 名称[_状态]序号.png 入库。
用法: python3 factory/split_sheet.py 拼图.png --name 蘑菇 [--state 烤] [--category 食物] [--size 1024]

算法：低分辨率 alpha 掩膜 → 闭合（补半透明缝）→ 8 连通域 → 每件只保留自己连通域内的像素（不是包围盒，邻件不会漏进来）
→ 面积相对中位数过小/过大的件拒收（碎片 / 多件粘连）→ 色相偏离全表中位数的件拒收（混入的配菜、叶子）。
拒收件存 source/rejects/ 并追加记录到 source/split-rejects.jsonl，供人复核；机器只拒不猜。
"""
import argparse, colorsys, json, math, time
from collections import deque
from pathlib import Path
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 4  # 低分辨率倍数


def components(mask, w, h):
    seen = bytearray(w * h); comps = []
    for i in range(w * h):
        if mask[i] and not seen[i]:
            q = deque([i]); seen[i] = 1; pts = []
            while q:
                j = q.popleft(); pts.append(j)
                x, y = j % w, j // w
                for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1),(x-1,y-1),(x+1,y+1),(x-1,y+1),(x+1,y-1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        k = ny * w + nx
                        if mask[k] and not seen[k]: seen[k] = 1; q.append(k)
            comps.append(pts)
    return comps


def mean_hsv(piece):
    """返回 (平均色相, 平均饱和度, 饱和像素的色相列表)。饱和像素 = s>0.3 且 alpha>128"""
    small = piece.resize((96, 96), Image.BOX)
    r = g = b = wsum = 0.0; hues = []
    for pr, pg, pb, pa in small.getdata():
        if pa > 128:
            r += pr; g += pg; b += pb; wsum += 1
            h, s, v = colorsys.rgb_to_hsv(pr / 255, pg / 255, pb / 255)
            if s > 0.3 and v > 0.15: hues.append(h * 360)
    if not wsum: return None
    h, s, v = colorsys.rgb_to_hsv(r / wsum / 255, g / wsum / 255, b / wsum / 255)
    return h * 360, s, hues


def circ_median_hue(hues):
    x = sum(math.cos(math.radians(h)) for h in hues); y = sum(math.sin(math.radians(h)) for h in hues)
    return math.degrees(math.atan2(y, x)) % 360


def hue_dist(a, b):
    d = abs(a - b) % 360; return min(d, 360 - d)


def extract_piece(im, alpha, pts, w, h, bbox):
    """只保留连通域 pts 自己的像素，返回带 6% 边距的 RGBA crop"""
    W, H = im.size
    buf = bytearray(w * h)
    for p in pts: buf[p] = 255
    m = Image.frombytes("L", (w, h), bytes(buf)).resize((W, H), Image.NEAREST).filter(ImageFilter.MaxFilter(9))
    piece = im.copy(); piece.putalpha(Image.composite(alpha, Image.new("L", (W, H), 0), m))
    pad = int(0.06 * max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
    return piece.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(W, bbox[2] + pad), min(H, bbox[3] + pad)))


def save_square(crop, path, size):
    side = max(crop.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
    target = int(size * 0.82)
    canvas = canvas.resize((target, target), Image.LANCZOS)
    final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    final.paste(canvas, ((size - target) // 2, (size - target) // 2))
    final.save(path)


def low_res_components(im, min_area):
    """返回 (alpha, w, h, comps)：低分辨率闭合掩膜上的 8 连通域"""
    W, H = im.size
    alpha = im.getchannel("A")
    small = alpha.resize((W // S, H // S), Image.BOX).point(lambda v: 255 if v > 12 else 0)
    small = small.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    w, h = small.size
    mask = bytes(1 if v else 0 for v in small.getdata())
    return alpha, w, h, [c for c in components(mask, w, h) if len(c) >= min_area * w * h]


def comp_bbox(pts, w):
    xs = [p % w for p in pts]; ys = [p // w for p in pts]
    return (min(xs) * S, min(ys) * S, (max(xs) + 1) * S, (max(ys) + 1) * S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet"); ap.add_argument("--name", required=True); ap.add_argument("--state", default="")
    ap.add_argument("--category", default="食物"); ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--min-area", type=float, default=0.0015, help="小于整图面积此比例的连通块直接视为噪点")
    ap.add_argument("--area-band", default="0.35,2.2", help="相对中位面积的接收区间")
    ap.add_argument("--hue-tol", type=float, default=45, help="色相偏离中位数超过此角度且饱和度>0.3 则拒收")
    ap.add_argument("--mix-tol", type=float, default=0.10, help="混色拒收的最低门槛；实际门槛 = max(此值, 3×整组中位 + 0.08)")
    ap.add_argument("--start", type=int, default=None); ap.add_argument("--out", default=str(ROOT / "assets"))
    a = ap.parse_args()
    lo, hi = (float(x) for x in a.area_band.split(","))

    sheet = Path(a.sheet)
    im = Image.open(sheet).convert("RGBA"); W, H = im.size
    alpha, w, h, comps = low_res_components(im, a.min_area)
    if not comps:
        print("SPLIT: 0 件（没有连通域）"); return
    areas = sorted(len(c) for c in comps); med = areas[len(areas) // 2]

    # 逐件抠出自己的像素
    pieces, rejects = [], []
    for pts in comps:
        bbox = comp_bbox(pts, w)
        area_ratio = len(pts) / med
        if area_ratio < lo:
            rejects.append(("碎片", bbox, f"面积 {area_ratio:.2f}× 中位数")); continue
        if area_ratio > hi:
            rejects.append(("疑似多件粘连", bbox, f"面积 {area_ratio:.2f}× 中位数")); continue
        crop = extract_piece(im, alpha, pts, w, h, bbox)
        pieces.append((bbox, crop, mean_hsv(crop)))

    # 色相离群（整件平均色偏离）+ 混色（件内有一块颜色偏离，如贴在番茄上的罗勒叶）
    hues = [hsv[0] for _, _, hsv in pieces if hsv and hsv[1] > 0.3]
    med_hue = circ_median_hue(hues) if len(hues) >= 3 else None
    # 每件的"偏离色相像素占比"。双色件（西葫芦皮/肉）整组都高，所以门槛相对整组中位数；配菜只贴在少数件上才会被拒
    def far_of(hsv):
        sat = hsv[2] if hsv else []
        return sum(1 for h in sat if hue_dist(h, med_hue) > 40) / len(sat) if len(sat) >= 200 else 0.0
    fars = sorted(far_of(hsv) for _, _, hsv in pieces) if med_hue is not None else [0.0]
    med_far = fars[len(fars) // 2]
    mix_thr = max(a.mix_tol, 3 * med_far + 0.08)
    accepted = []
    for bbox, crop, hsv in pieces:
        if med_hue is not None and hsv:
            if hsv[1] > 0.3 and hue_dist(hsv[0], med_hue) > a.hue_tol:
                rejects.append(("颜色离群（配菜/叶子？）", bbox, f"色相 {hsv[0]:.0f}° vs 中位 {med_hue:.0f}°")); continue
            far = far_of(hsv)
            if far > mix_thr:
                rejects.append(("混色（贴着配菜？）", bbox, f"偏离色相像素 {far:.0%}，整组中位 {med_far:.0%}，门槛 {mix_thr:.0%}")); continue
        accepted.append((bbox, crop))
    accepted.sort(key=lambda t: (round((t[0][1] + t[0][3]) / 2 / (H / 4)), t[0][0]))  # 按行再按列，编号稳定

    # 落盘
    out_dir = Path(a.out) / a.category; out_dir.mkdir(parents=True, exist_ok=True)
    stem = a.name + (f"_{a.state}" if a.state else "")
    existing = sorted(int(p.stem[len(stem):]) for p in out_dir.glob(f"{stem}*.png") if p.stem[len(stem):].isdigit())
    idx = a.start if a.start is not None else (existing[-1] + 1 if existing else 1)
    for bbox, crop in accepted:
        save_square(crop, out_dir / f"{stem}{idx}.png", a.size); idx += 1

    rej_dir = ROOT / "source/rejects"; rej_dir.mkdir(parents=True, exist_ok=True)
    with (ROOT / "source/split-rejects.jsonl").open("a", encoding="utf-8") as f:
        for i, (reason, bbox, detail) in enumerate(rejects, 1):
            p = rej_dir / f"{sheet.stem}_reject{i}.png"; im.crop(bbox).save(p)
            f.write(json.dumps({"sheet": str(sheet.relative_to(ROOT)) if sheet.is_relative_to(ROOT) else str(sheet),
                                "target": stem, "reason": reason, "detail": detail, "bbox": bbox, "file": str(p.relative_to(ROOT)),
                                "ts": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False) + "\n")
    print(f"SPLIT: {len(accepted)} 件，拒收 {len(rejects)}" + (f"（{'，'.join(sorted(set(r[0] for r in rejects)))}）" if rejects else ""))


if __name__ == "__main__":
    main()
