#!/usr/bin/env python3
"""月亮（参考视频）的程序化查询与保真度量。原片在 source/videos/<组>/<id>.mp4（不入库，sha256 登记在同目录 videos.sha256）。

  .venv/bin/python factory/moon.py list                              # 有哪些月亮：id、组、sha256 是否与登记一致、存盘分辩率/帧率/时长
  .venv/bin/python factory/moon.py frame ZXcNxjulej0 64              # 取第 64 秒那一帧：打印 md5 与均色，存 reports/moon/<id>-64.png；反复跑同一答案
  .venv/bin/python factory/moon.py frame ZXcNxjulej0 64 --crop 0.2,0.3,0.6,0.7   # 只看某个区域（归一化 x0,y0,x1,y1）
  .venv/bin/python factory/moon.py fidelity ZXcNxjulej0              # 量月亮自己准不准：向源站取原片规格（不下载），与存盘对比缩放比/帧率/时长偏差 → videos.meta.json
  .venv/bin/python factory/moon.py fidelity --all

判据：MOON-FIDELITY 行给出 scale=存盘宽/原片宽、fps 差、时长差；缩放 <1 表示我们学的是缩小版，比对细节（小字、细线）时要打折。
"""
import argparse, hashlib, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "source/videos"


def find(vid):
    hits = list(VID.glob(f"*/{vid}.*"))
    hits = [h for h in hits if h.suffix in (".mp4", ".webm", ".mkv")]
    if not hits: sys.exit(f"找不到月亮 {vid}（source/videos/*/{vid}.mp4）；它不入库，只在采集机上")
    return hits[0]


def ledger_entry(path: Path):
    led = path.parent / "videos.sha256"
    if not led.exists(): return None
    for l in led.read_text(encoding="utf-8").splitlines():
        parts = l.split()
        if len(parts) >= 2 and parts[1] == path.name: return {"sha256": parts[0], "url": parts[2] if len(parts) > 2 else None}
    return None


def probe(path: Path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    info = {"w": int(cap.get(3)), "h": int(cap.get(4)), "fps": round(cap.get(cv2.CAP_PROP_FPS), 3), "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}
    info["duration_s"] = round(info["frames"] / info["fps"], 1) if info["fps"] else None
    cap.release(); return info


def cmd_list(a):
    rows = []
    for p in sorted(VID.glob("*/*.mp4")):
        le = ledger_entry(p); digest = hashlib.sha256(p.read_bytes()).hexdigest()
        pr = probe(p)
        rows.append((p.parent.name, p.stem, "✓" if le and le["sha256"] == digest else ("✗ 与登记不符" if le else "未登记"), f"{pr['w']}x{pr['h']}", pr["fps"], pr["duration_s"], (le or {}).get("url")))
    print(f"{'组':20} {'id':14} {'sha256':10} {'存盘':10} {'fps':7} {'秒':7} url")
    for r in rows: print(f"{r[0]:20} {r[1]:14} {r[2]:10} {r[3]:10} {str(r[4]):7} {str(r[5]):7} {r[6] or ''}")
    print(f"MOONS: {len(rows)}")


def cmd_frame(a):
    import cv2
    p = find(a.video); cap = cv2.VideoCapture(str(p))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(a.sec) * 1000); ok, fr = cap.read(); cap.release()
    if not ok: sys.exit(f"取帧失败：{p} @ {a.sec}s")
    h, w = fr.shape[:2]
    if a.crop:
        x0, y0, x1, y1 = [float(v) for v in a.crop.split(",")]
        fr = fr[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    out = ROOT / "reports/moon"; out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{a.video}-{a.sec}{'-crop' if a.crop else ''}.png"; cv2.imwrite(str(dst), fr)
    md5 = hashlib.md5(fr.tobytes()).hexdigest(); mean = [round(float(x), 1) for x in fr.mean(axis=(0, 1))]
    print(f"MOON-FRAME {a.video} t={a.sec}s size={fr.shape[1]}x{fr.shape[0]} md5={md5} mean_bgr={mean} → {dst.relative_to(ROOT)}")


def cmd_fidelity(a):
    targets = [p for p in sorted(VID.glob("*/*.mp4"))] if a.all else [find(a.video)]
    for p in targets:
        le = ledger_entry(p) or {}; url = le.get("url") or f"https://youtu.be/{p.stem}"
        local = probe(p); local["sha256_ok"] = (hashlib.sha256(p.read_bytes()).hexdigest() == le.get("sha256")) if le else None
        meta = {"id": p.stem, "url": url, "stored": local, "ts": time.strftime("%F %T")}
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True}) as y:
                info = y.extract_info(url, download=False)
            fmts = [f for f in info.get("formats", []) if f.get("vcodec") not in (None, "none") and f.get("height")]
            best = max(fmts, key=lambda f: (f.get("height") or 0, f.get("fps") or 0)) if fmts else {}
            meta["original"] = {"w": best.get("width"), "h": best.get("height"), "fps": best.get("fps"), "duration_s": info.get("duration"), "title": info.get("title")}
            ow, oh = best.get("width") or 0, best.get("height") or 0
            meta["scale"] = round(local["w"] / ow, 3) if ow else None
            meta["fps_delta"] = round((local["fps"] or 0) - (best.get("fps") or 0), 2) if best.get("fps") else None
            meta["duration_delta_s"] = round((local["duration_s"] or 0) - (info.get("duration") or 0), 1) if info.get("duration") else None
            meta["crop"] = "none（等比缩放，无裁切）" if ow and oh and abs(local["w"] / local["h"] - ow / oh) < 0.02 else "aspect 不一致，可能有裁切/黑边"
            print(f"MOON-FIDELITY {p.stem}: 存盘 {local['w']}x{local['h']}@{local['fps']} vs 原片 {ow}x{oh}@{best.get('fps')} · scale={meta['scale']} fps_delta={meta['fps_delta']} duration_delta={meta['duration_delta_s']}s · {meta['crop']} · sha256 {'✓' if local['sha256_ok'] else '✗'}")
        except Exception as e:
            meta["original"] = None; meta["error"] = str(e)[:200]
            print(f"MOON-FIDELITY {p.stem}: 取不到原片规格（{str(e)[:80]}）；存盘 {local['w']}x{local['h']}@{local['fps']} · sha256 {'✓' if local['sha256_ok'] else '✗'}")
        mp = p.parent / "videos.meta.json"
        allm = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
        allm[p.stem] = meta; mp.write_text(json.dumps(allm, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("frame"); f.add_argument("video"); f.add_argument("sec", type=float); f.add_argument("--crop", default=None)
    d = sub.add_parser("fidelity"); d.add_argument("video", nargs="?"); d.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.cmd == "fidelity" and not a.all and not a.video: ap.error("给 video id 或 --all")
    {"list": cmd_list, "frame": cmd_frame, "fidelity": cmd_fidelity}[a.cmd](a)


if __name__ == "__main__":
    main()
