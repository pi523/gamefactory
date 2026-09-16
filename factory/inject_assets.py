#!/usr/bin/env python3
"""把素材注入游戏 index.html 的 window.BF_ASSETS（玩法不动，只换视图层）。
优先级：games/<id>/assets/manifest.json（游戏专属，含 __scene 背景）> assets/manifest.json（公共库）。
用法: python3 factory/inject_assets.py games/<id> [--state 切块] [--max 4]
物件名取 prd.json 的 assets[].name（兜底扫 game.js 的 kind: '中文' 字面量）；一个都没注入则退出码 1。
"""
import argparse, json, os, re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pick(entry, state, maxn):
    files = entry.get(state) or entry.get("默认") or next(iter(entry.values()))
    return files[:maxn]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_dir"); ap.add_argument("--state", default="切块"); ap.add_argument("--max", type=int, default=4)
    ap.add_argument("--kinds", nargs="*")
    a = ap.parse_args()
    game = Path(a.game_dir).resolve()
    kinds = a.kinds
    if not kinds and (game / "prd.json").exists():
        kinds = [x["name"] for x in json.loads((game / "prd.json").read_text(encoding="utf-8")).get("assets", [])]
    if not kinds:
        kinds = sorted(set(re.findall(r"kind:\s*'([^']+)'", (game / "game.js").read_text(encoding="utf-8"))))

    local_path = game / "assets/manifest.json"
    local = json.loads(local_path.read_text(encoding="utf-8")) if local_path.exists() else {}
    sp = ROOT / "assets/manifest.json"; shared = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}   # 公共素材库可选
    rel_root = os.path.relpath(ROOT, game).replace(os.sep, "/")
    inj = {}
    kinds = list(kinds) + [n for n in (local.get("效果") or {}) if n not in kinds]          # 效果层（原地生成的火苗/蒸汽）不在 PRD 里
    kinds += [n for cat, names in local.items() if not cat.startswith("__") and isinstance(names, dict) for n in names if n.endswith("·空位") and n not in kinds]   # 备料空位补丁
    for k in kinds:
        src = None
        for cat, names in local.items():
            if cat.startswith("__") or not isinstance(names, dict): continue           # __scene/__layout/__wokcrop 等元信息不是类别
            if k in names: src = ("local", names[k]); break
        if not src:
            for cat, names in shared.items():
                if k in names: src = ("shared", names[k]); break
        if not src:
            print(f"  {k}: 两个库都没有，走占位色块"); continue
        entry = src[1]; pre = "./" if src[0] == "local" else f"{rel_root}/"
        real_states = [s for s in entry if s != "默认"]
        if len(real_states) >= 2:   # 多状态物件（生/金黄/焦…）→ 对象，运行时 sp.setState 切换
            inj[k] = {s: [pre + f for f in entry[s][: a.max]] for s in entry}
            print(f"  {k}: {sum(len(v) for v in inj[k].values())} 张 · 状态 {list(inj[k])}（{'游戏专属' if src[0]=='local' else '公共库'}）")
        else:
            files = pick(entry, a.state, a.max)
            inj[k] = [pre + f for f in files]
            print(f"  {k}: {len(inj[k])} 张（{'游戏专属' if src[0]=='local' else '公共库'}）")
    if local.get("__scene"):
        inj["__scene"] = {o: f"./{p}" for o, p in local["__scene"].items()}
        print(f"  __scene: {list(inj['__scene'])}")
    sp = game / "style.json"
    if sp.exists():
        sty = json.loads(sp.read_text(encoding="utf-8"))
        inj["__style"] = {k: sty[k] for k in ("ui_palette", "ui_radius", "ui_font", "art_style", "mood") if k in sty}
        print(f"  __style: {sty.get('art_style','')[:20]} · {sty.get('ui_palette',{})}")
    lp = game / "assets/layout.json"
    if lp.exists():
        lay = json.loads(lp.read_text(encoding="utf-8"))
        inj["__layout"] = {k: lay[k] for k in ("type", "slots", "points", "width", "img_w", "img_h", "pantry", "pantry_mode", "effects", "counter_top") if k in lay}   # slots 内含 pool（油面），pantry 为备料台锚点
        for flag in ("__wokcrop", "__pantry"):                                          # 引擎据此决定摆法（原地生成图：原位原尺寸、不羽化不投影）
            if local.get(flag): inj[flag] = True
        print(f"  __layout: {lay['type']} × {len(lay.get('slots') or lay.get('points') or [])}")
    def _ver(u):   # 缓存穿透：按文件 mtime 加版本号（同名换图时浏览器才会重新拉）
        try:
            fp = (game / u[2:]) if u.startswith("./") else (ROOT / u.split("/", 3)[-1] if u.startswith("../../") else None)
            return f"{u}?v={int(fp.stat().st_mtime)}" if fp and fp.exists() else u
        except Exception: return u
    for k, v in list(inj.items()):
        if k == "__scene": inj[k] = {o: _ver(u) for o, u in v.items()}
        elif k.startswith("__") or not isinstance(v, (dict, list)): continue
        elif isinstance(v, dict): inj[k] = {s: [_ver(u) for u in urls] for s, urls in v.items()}
        else: inj[k] = [_ver(u) for u in v]
    idx = game / "index.html"; t = idx.read_text(encoding="utf-8")
    new = "window.BF_ASSETS = " + json.dumps(inj, ensure_ascii=False) + ";"
    t2, n = re.subn(r"window\.BF_ASSETS\s*=\s*\{.*?\};", new, t, count=1, flags=re.S)
    if n != 1: raise SystemExit("index.html 里找不到 window.BF_ASSETS = {...}; 锚点")
    import re as _re; stamp = str(int(time.time()))
    t2 = _re.sub(r'src="\./game\.js(\?v=\d+)?"', f'src="./game.js?v={stamp}"', t2)
    idx.write_text(t2, encoding="utf-8")
    n_obj = sum((sum(len(x) for x in v.values()) if isinstance(v, dict) else len(v)) for k, v in inj.items() if not k.startswith("__") and isinstance(v, (dict, list)))
    print("注入完成 →", idx.relative_to(ROOT), f"（{n_obj} 张物件{'，含背景' if '__scene' in inj else ''}）")
    if not inj: raise SystemExit("INJECT: EMPTY —— 没有任何物件被注入")


if __name__ == "__main__":
    main()
