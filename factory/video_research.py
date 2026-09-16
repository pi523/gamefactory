#!/usr/bin/env python3
"""视频找月亮：搜索/下载竞品实机视频 → 1fps 抽帧 → 拼图 → 视觉模型逐张描述 → 结构化为 [视频抽帧] 证据并入 research.json。
用法:
  .venv/bin/python factory/video_research.py --id bbq-skewer --query "Master Grill mobile gameplay"      # 搜 YouTube
  .venv/bin/python factory/video_research.py --id bbq-skewer --url https://youtu.be/xxxx                 # 指定视频
  .venv/bin/python factory/video_research.py --id bbq-skewer --file source/videos/mine.mp4               # 自己录的
  不带 --query/--url/--file 时，用 research.json 里前 2 个竞品名各搜一段。
视频只下视频轨（≤480p，无音频），存 source/videos/<id>/（不进仓库），登记 sha256；拼图存 games/<id>/video/ 供人复核。
"""
import argparse, hashlib, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402

SHEET_Q = ("这是手机游戏《{name}》实机录像的关键帧拼图（每格左上角为时间戳，秒）。只根据画面回答，看不清写“未见”，不要脑补。只输出 JSON：\n"
           '{{"gameplay_frames":[时间戳列表，只列真正在玩的帧，排除菜单/加载/结算],'
           '"core_loop":"玩家做什么→发生什么，一两句",'
           '"cadence":[{{"what":"目标/订单/敌人出现或消失","t":[时间戳...],"interval_s":数字或null}}],'
           '"hud":[{{"item":"分数/命/计时/金币/进度","where":"左上/顶中/右上/…","how":"数字/图标/条"}}],'
           '"feedback":{{"hit":"命中时画面反馈或未见","miss":"失误时画面反馈或未见","combo":"连击表现或未见"}},'
           '"fail_state":"失败/结束条件的画面证据或未见",'
           '"difficulty":"压力如何随时间体现，带时间戳",'
           '"camera":"竖屏/横屏、视角、是否固定",'
           '"numbers":[{{"item":"如 命数/倒计时初值/目标出现间隔","value":"","t":时间戳}}]}}')

STYLE_Q = ("这是手机游戏《{name}》实机录像的关键帧拼图。只根据画面描述它的**美术与 UI 风格**，用于让另一款游戏模仿风格（不是复制素材）。只输出 JSON：\n"
           '{{"art_style":"写实/卡通/低多边形/手绘/像素/2.5D 等，一句话定性",'
           '"render":"3D 还是 2D，光照与阴影特点（平光/柔和/强对比/描边）",'
           '"palette_desc":"主色调与配色关系（如 高饱和暖黄橙 + 木纹棕，点缀绿）",'
           '"mood":"明亮欢快/温暖治愈/暗黑写实/清爽简洁…",'
           '"camera":"视角、俯仰角、是否固定",'
           '"ui_style":"HUD/按钮/面板的形状、圆角、描边、配色、字体感觉（如 白底圆角卡片+粗黑体数字）",'
           '"props_style":"食材/道具的造型语言（Q 版夸张/写实/简化图标）",'
           '"background_style":"背景的复杂度与处理（模糊/清晰、装饰密度）",'
           '"style_prompt_en":"一段 60 词内的英文生图风格提示，可直接拼进 image prompt",'
           '"ui_palette":{{"bg":"#hex","panel":"#hex","accent":"#hex","text":"#hex","danger":"#hex"}}}}')


def palette_kmeans(frames, k=6, sample=40):
    """客观色板：从游玩帧均匀抽样像素做 k-means，返回 [(hex, 占比)]，按占比降序。"""
    import cv2, numpy as np
    pts = []
    for _, fr in frames[:: max(1, len(frames) // sample)]:
        small = cv2.resize(fr, (64, 36)); pts.append(small.reshape(-1, 3))
    if not pts: return []
    data = np.vstack(pts).astype(np.float32)
    _, labels, centers = cv2.kmeans(data, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k) / len(labels)
    out = []
    for c, n in sorted(zip(centers, counts), key=lambda z: -z[1]):
        b, g, r = (int(x) for x in c); out.append((f"#{r:02x}{g:02x}{b:02x}", round(float(n), 3)))
    return out


MERGE_Q = ("把同一视频多张拼图的观察合并成一份结论，只输出 JSON，字段同输入；cadence 的 interval_s 取各张的中位数；"
           "numbers 去重；所有字段只保留有时间戳证据的内容，冲突处保留两种说法并标注时间戳。\n\n{parts}")


def sha256(p: Path):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def search(query, n=6):
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "noprogress": True}) as y:
        r = y.extract_info(f"ytsearch{n}:{query}", download=False)
    vids = []
    for e in r.get("entries", []):
        d = e.get("duration") or 0; title = e.get("title") or ""
        score = 0
        if 60 <= d <= 480: score += 3
        elif d <= 900: score += 1
        if re.search(r"gameplay|实机|试玩|walkthrough|play|攻略|level", title, re.I): score += 2
        if re.search(r"trailer|预告|review|评测|reaction|ASMR", title, re.I): score -= 3
        vids.append((score, d, title, f"https://youtu.be/{e.get('id')}"))
    vids.sort(key=lambda v: (-v[0], v[1]))
    return vids


def download(url, out: Path):
    import yt_dlp
    out.mkdir(parents=True, exist_ok=True)
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
            "format": "bestvideo[height<=480][ext=mp4]/bestvideo[height<=480]/bestvideo[height<=720]/best[height<=480]",
            "outtmpl": str(out / "%(id)s.%(ext)s")}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
        return Path(y.prepare_filename(info)), info.get("title", ""), info.get("duration") or 0


def frames_1fps(path: Path):
    import cv2
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 30; step = max(1, int(round(fps)))
    out = []; i = 0
    while cap.grab():
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok: out.append((i / fps, fr))
        i += 1
    cap.release(); return out


def make_sheets(frames, dst_dir: Path, per=12, max_sheets=4):
    """跳过头尾各 5%，均匀取 per*max_sheets 帧拼成 4×3 图"""
    import cv2
    from PIL import Image, ImageDraw
    if not frames: return []
    lo, hi = int(len(frames) * 0.05), int(len(frames) * 0.95)
    pool = frames[lo:hi] or frames
    want = min(len(pool), per * max_sheets)
    idx = [int(k * (len(pool) - 1) / max(1, want - 1)) for k in range(want)]
    picked = [pool[k] for k in idx]
    dst_dir.mkdir(parents=True, exist_ok=True); sheets = []
    fh, fw = picked[0][1].shape[:2]
    portrait = fh > fw
    tw, th, cols = (202, 360, 6) if portrait else (320, 180, 4)     # 竖屏帧用竖格子，不压扁
    rows = -(-per // cols)
    for s in range(0, len(picked), per):
        chunk = picked[s:s + per]; im = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20)); d = ImageDraw.Draw(im)
        for k, (ts, fr) in enumerate(chunk):
            p = Image.fromarray(cv2.cvtColor(cv2.resize(fr, (tw, th)), cv2.COLOR_BGR2RGB)); im.paste(p, ((k % cols) * tw, (k // cols) * th))
            d.text(((k % cols) * tw + 6, (k // cols) * th + 4), f"t={ts:.0f}s", fill=(0, 255, 120))
        p = dst_dir / f"sheet{len(sheets) + 1}.jpg"; im.save(p, quality=85); sheets.append(p)
    return sheets


def observe_style(name, sheets, gid):
    try:
        return llm.chat_json([{"role": "user", "content": [{"type": "text", "text": STYLE_Q.format(name=name)}] + [llm.image_part(str(s)) for s in sheets[:2]]}],
                             role="vision", max_tokens=4000, tag=f"video:{gid}:style")
    except Exception as e:
        print("   ✗ 风格观察失败:", str(e)[:120]); return None


def analyze(name, sheets, gid):
    parts = []
    for i in range(0, len(sheets), 2):
        chunk = sheets[i:i + 2]
        try:
            d = llm.chat_json([{"role": "user", "content": [{"type": "text", "text": SHEET_Q.format(name=name)}] + [llm.image_part(str(s)) for s in chunk]}],
                              role="vision", max_tokens=6000, tag=f"video:{gid}:sheet")
            parts.append(d)
        except Exception as e:
            print("   ✗ 拼图分析失败:", str(e)[:160])
    if not parts: return None
    if len(parts) == 1: return parts[0]
    try:
        return llm.chat_json([{"role": "user", "content": MERGE_Q.format(parts=json.dumps(parts, ensure_ascii=False))}], role="cheap", max_tokens=6000, tag=f"video:{gid}:merge")
    except Exception as e:
        print("   ✗ 合并失败，保留第一张:", str(e)[:120]); return parts[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True); ap.add_argument("--query", action="append", default=[]); ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--file", action="append", default=[]); ap.add_argument("--max", type=int, default=2, help="最多分析几段视频")
    ap.add_argument("--style-only", action="store_true", help="不重新搜/下，只给 research.json 里已有的相关视频补风格观察（用本地已下载文件抽帧）")
    ap.add_argument("--include-irrelevant", action="store_true", help="--style-only 时也给机制不相关的视频学风格（只借画风时用）")
    a = ap.parse_args()
    if a.style_only:
        game = ROOT / "games" / a.id; rp = game / "research.json"; research = json.loads(rp.read_text(encoding="utf-8"))
        vdir = ROOT / "source/videos" / a.id
        for v in research.get("videos", []):
            if not v.get("relevant", True) and not a.include_irrelevant: continue
            vid_id = v["video"].rstrip("/").split("/")[-1].split("=")[-1]
            local = next(iter(vdir.glob(f"{vid_id}.*")), None)
            if not local: print(f"  跳过（本地无文件）: {v['title'][:40]}"); continue
            frames = frames_1fps(local); sheets = [ROOT / s for s in v.get("sheets", [])] or make_sheets(frames, game / "video" / local.stem)
            sty = observe_style(v.get("title", ""), sheets, a.id)
            if sty:
                sty["palette_kmeans"] = palette_kmeans(frames); v["style"] = sty
                print(f"  {v['title'][:40]} → 风格：{sty.get('art_style','')[:30]} · {sty.get('mood','')[:14]} · 色板 {[c for c,_ in sty['palette_kmeans'][:5]]}")
        rp.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8"); print("STYLE: 已写入 research.json"); return
    game = ROOT / "games" / a.id; game.mkdir(parents=True, exist_ok=True)
    vdir = ROOT / "source/videos" / a.id; vdir.mkdir(parents=True, exist_ok=True)
    rp = game / "research.json"; research = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {"topic": a.id}

    jobs = []  # (name, source, kind)
    for u in a.url: jobs.append((u, u, "url"))
    for f in a.file: jobs.append((Path(f).stem, f, "file"))
    queries = list(a.query)
    if not jobs and not queries:
        queries = [f"{m['name']} gameplay" for m in research.get("moons", [])[:2]] or [f"{research.get('topic', a.id)} 手游 实机"]
    for q in queries:
        vids = search(q)
        if not vids: print(f"  搜索无结果: {q}"); continue
        best = vids[0]; print(f"  搜索「{q}」→ 选 {best[2][:50]} ({best[1]/60:.1f}min) {best[3]}")
        jobs.append((q, best[3], "url"))
    jobs = jobs[: a.max]

    results = research.setdefault("videos", []); ledger = vdir / "videos.sha256"
    for name, src, kind in jobs:
        t0 = time.time()
        try:
            if kind == "file": path, title, dur = Path(src), Path(src).name, 0
            else: path, title, dur = download(src, vdir)
        except Exception as e:
            print(f"  ✗ 下载失败 {src}: {str(e)[:120]}"); continue
        digest = sha256(path); ledger.open("a", encoding="utf-8").write(f"{digest}  {path.name}  {src}\n")
        frames = frames_1fps(path)
        sheets = make_sheets(frames, game / "video" / path.stem)
        print(f"  {title[:50]} · {dur/60:.1f}min · 抽帧 {len(frames)} · 拼图 {len(sheets)} ({time.time()-t0:.0f}s)")
        d = analyze(title or name, sheets, a.id)
        if not d: continue
        sty = observe_style(title or name, sheets, a.id)
        if sty:
            sty["palette_kmeans"] = palette_kmeans(frames)
            d["style"] = sty
            print(f"    风格：{sty.get('art_style','')[:30]} · {sty.get('mood','')[:16]} · 色板 {[c for c,_ in sty['palette_kmeans'][:4]]}")
        # 机制相关性：标题匹配不等于同机制（搜"たこ焼き ゲーム"搜到过恐怖游戏）
        try:
            rel = llm.chat_json([{"role": "user", "content": f"题材：「{research.get('topic', a.id)}」。下面是一段视频的实机观察：{json.dumps({k: d.get(k) for k in ('core_loop', 'cadence', 'camera')}, ensure_ascii=False)[:1500]}\n"
                                 "它和题材是否是同一类玩法机制（可作为复刻参考）？只输出 JSON {\"relevant\": true/false, \"why\": \"一句话\"}"}], role="cheap", max_tokens=300, tag=f"video:{a.id}:relevance")
            d["relevant"] = bool(rel.get("relevant")); d["relevance_why"] = rel.get("why", "")
        except Exception as e:
            d["relevant"] = True; d["relevance_why"] = f"判定失败，默认相关: {str(e)[:60]}"
        print(f"    相关性：{'✓ 同机制' if d['relevant'] else '✗ 不相关，保真比对将跳过'} — {d.get('relevance_why', '')[:70]}")
        d.update({"video": src, "title": title, "duration_s": dur, "sha256": digest, "sheets": [str(s.relative_to(ROOT)) for s in sheets],
                  "evidence": "[视频抽帧]", "ts": time.strftime("%F %T")})
        results = [v for v in results if v.get("video") != src] + [d]; research["videos"] = results
        print(f"    循环：{str(d.get('core_loop', ''))[:80]}")
        for c in d.get("cadence", [])[:3]: print(f"    节奏：{c.get('what')} ≈ {c.get('interval_s')}s @ {c.get('t', [])[:4]}")
        print(f"    数值 {len(d.get('numbers', []))} 条 · 失败态：{str(d.get('fail_state', ''))[:50]}")
    rp.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"\n## 视频抽帧（{time.strftime('%F %T')}）\n"]
    for v in research.get("videos", []):
        md.append(f"### {v.get('title')} · {v.get('video')}\n- 核心循环：{v.get('core_loop')}\n- 节奏：" + "；".join(f"{c.get('what')}≈{c.get('interval_s')}s" for c in v.get("cadence", []))
                  + f"\n- HUD：" + "；".join(f"{h.get('item')}@{h.get('where')}" for h in v.get("hud", []))
                  + f"\n- 反馈：{json.dumps(v.get('feedback'), ensure_ascii=False)}\n- 失败态：{v.get('fail_state')}\n- 难度：{v.get('difficulty')}\n- 镜头：{v.get('camera')}\n- 数值："
                  + "；".join(f"{n.get('item')}={n.get('value')}@t{n.get('t')}" for n in v.get("numbers", [])) + f"\n- 拼图：{', '.join(v.get('sheets', []))}\n")
    (game / "research.md").open("a", encoding="utf-8").write("\n".join(md))
    print(f"VIDEO: {len(research.get('videos', []))} 段视频入研 → games/{a.id}/research.json")


if __name__ == "__main__":
    main()
