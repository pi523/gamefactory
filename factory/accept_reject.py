#!/usr/bin/env python3
"""人复核后放行拒收件：按 source/split-rejects.jsonl 的行号（从 1 起）重新抠图入库，并在台账里标 accepted。
用法: python3 factory/accept_reject.py 14 15 16 [--by 复核人]
"""
import argparse, json, sys, time
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import split_sheet as ss  # noqa: E402


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("lines", nargs="+", type=int); ap.add_argument("--by", default="human")
    ap.add_argument("--category", default="食物"); ap.add_argument("--size", type=int, default=1024)
    a = ap.parse_args()
    ledger = ROOT / "source/split-rejects.jsonl"
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    cache = {}
    for n in a.lines:
        r = rows[n - 1]
        if r.get("accepted"): print(f"#{n} 已放行过，跳过"); continue
        sheet = ROOT / r["sheet"]
        if sheet not in cache:
            im = Image.open(sheet).convert("RGBA"); cache[sheet] = (im,) + ss.low_res_components(im, 0.0015)
        im, alpha, w, h, comps = cache[sheet]
        pts = next((c for c in comps if list(ss.comp_bbox(c, w)) == list(r["bbox"])), None)
        if pts is None: print(f"#{n} 在原图里找不到同 bbox 的连通域，跳过"); continue
        crop = ss.extract_piece(im, alpha, pts, w, h, tuple(r["bbox"]))
        out_dir = ROOT / "assets" / a.category
        stem = r["target"]
        existing = sorted(int(p.stem[len(stem):]) for p in out_dir.glob(f"{stem}*.png") if p.stem[len(stem):].isdigit())
        idx = (existing[-1] + 1) if existing else 1
        dst = out_dir / f"{stem}{idx}.png"; ss.save_square(crop, dst, a.size)
        r["accepted"] = {"by": a.by, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "file": str(dst.relative_to(ROOT))}
        print(f"#{n} {r['reason']} → 放行 {dst.relative_to(ROOT)}")
    ledger.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
