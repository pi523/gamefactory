#!/usr/bin/env python3
"""黑灯工厂检验器 v2：静态层 → 浏览器层（竖屏 stage 检查）→ 可玩通层（笨玩家）→ 物理层（目标必须落在布局锚点上）。
用法: python3 factory/verify.py games/<id> [--rules specs/rules/h5-hard-rules.json] [--out reports]
退出码 0=PASS 1=FAIL 2=检验器自身出错。最后一行固定打印 VERDICT: PASS|FAIL
"""
import argparse, glob, http.server, io, json, math, re, socket, socketserver, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import bot  # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def serve(root, port):
    handler = lambda *a, **k: QuietHandler(*a, directory=str(root), **k)
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ---------------- 静态层 ----------------
def static_checks(game_dir: Path, rules):
    fails, info = [], {}
    files = []
    for g in rules["scan_globs"]:
        files += [Path(p) for p in glob.glob(str(game_dir / "**" / g), recursive=True) if "/attempts/" not in p]
    if not (game_dir / "index.html").exists():
        return ["缺少 index.html"], info
    total = sum(p.stat().st_size for p in game_dir.rglob("*") if p.is_file() and "attempts" not in p.parts)
    info["total_bytes"] = total
    if total > rules["max_total_bytes"]:
        fails.append(f"包体 {total} B 超过上限 {rules['max_total_bytes']} B")
    blob = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files)
    if "bf-runtime.js" in blob or "bf-lesson.js" in blob:   # 用了共享运行时/教学课引擎：契约等必需内容由它们提供，算进扫描范围
        for vf in ("vendor/bf-runtime.js", "vendor/bf-lesson.js"):
            rt = ROOT / vf
            if rt.exists() and vf.split("/")[-1] in blob: blob += "\n" + rt.read_text(encoding="utf-8")
        blob += "\n" + (ROOT / "vendor/bf-runtime.js").read_text(encoding="utf-8")
        for p in files:                # 玩法层越权：直接碰 DOM / three 场景
            if p.suffix != ".js": continue
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for pat in rules.get("runtime_forbid_patterns", []):
                    if re.search(pat, line):
                        fails.append(f"玩法层越权（运行时游戏禁止 /{pat}/）: {p.relative_to(game_dir)}:{i}")
    for pat in rules["forbid_patterns"]:
        for p in files:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.search(pat, line):
                    fails.append(f"禁用模式 /{pat}/ 出现在 {p.relative_to(game_dir)}:{i}")
    for s in rules["require_strings"]:
        if s not in blob:
            fails.append(f"缺少必需内容: {s}")
    for m in re.finditer(r"""(?:import\s+[^'"]*from\s*|import\s*\(\s*|src=)['"]([^'"]+)['"]""", blob):
        spec = m.group(1)
        if spec == "three" or spec.startswith("data:"):
            continue
        if not any(spec.startswith(pfx) for pfx in rules["allowed_import_prefixes"]):
            fails.append(f"非相对路径引用: {spec}")
    return fails, info


# ---------------- stage / layout ----------------
def stage_rect(page, sel):
    return page.evaluate("(sel)=>{const e=document.querySelector(sel); if(!e) return null; const b=e.getBoundingClientRect(); return {x:b.x,y:b.y,w:b.width,h:b.height}}", sel)


def stage_checks(rect, rs, W, H):
    if not rect: return [f"缺少 {rs['selector']} 容器（游戏必须包在固定竖屏 stage 里）"]
    fails = []
    ar = rect["w"] / max(1, rect["h"])
    if not (rs["aspect_min"] <= ar <= rs["aspect_max"]):
        fails.append(f"{rs['selector']} 宽高比 {ar:.3f} 不在 [{rs['aspect_min']},{rs['aspect_max']}]，必须是手机竖屏比例")
    vp_ar = W / H
    if rs["aspect_min"] <= vp_ar <= rs["aspect_max"]:   # 手机：铺满
        if rect["w"] < 0.98 * W or rect["h"] < 0.98 * H:
            fails.append(f"手机视口下 stage 未铺满 ({rect['w']:.0f}x{rect['h']:.0f} vs {W}x{H})")
    else:                                                # 宽屏：占满高度、居中、两侧留黑
        if rect["h"] < rs["min_height_ratio"] * H:
            fails.append(f"宽屏下 stage 高度 {rect['h']:.0f} 未占满视口高 {H}")
        if abs((rect["x"] + rect["w"] / 2) - W / 2) > rs["center_tolerance_px"]:
            fails.append(f"宽屏下 stage 未水平居中 (中心 x={rect['x']+rect['w']/2:.0f}, 视口中心 {W/2:.0f})")
        if rect["w"] > 0.7 * W:
            fails.append(f"宽屏下 stage 宽 {rect['w']:.0f} 铺得太开，不像手机屏")
    return fails


def cover_map(layout, rect):
    """背景图 background-size:cover 到 stage 的映射：归一化 (nx,ny) → 视口 CSS px"""
    iw, ih = layout.get("img_w", 9), layout.get("img_h", 16)
    s = max(rect["w"] / iw, rect["h"] / ih)
    w, h = iw * s, ih * s
    ox, oy = rect["x"] + (rect["w"] - w) / 2, rect["y"] + (rect["h"] - h) / 2
    return lambda nx, ny: (ox + nx * w, oy + ny * h), s * iw  # 返回映射函数和"图宽对应的像素"


def layout_checks(page, layout, rl, rect, extra_samples=None):
    """playing 期间多次采样 targets（加上机器人游玩全程的快照），anchored 目标中心必须贴着锚点；drag 目标的 to 必须是锚点。"""
    to_px, img_px_w = cover_map(layout, rect)
    page.evaluate("() => { window.__bf.setTimeScale(1); window.__bf.reset(7); window.__bf.start(); }")
    page.wait_for_timeout(700)
    raw = list(extra_samples or [])
    for _ in range(6):
        st = page.evaluate("() => window.__bf.state()")
        raw += st["targets"]; page.wait_for_timeout(350)
    samples = [t for t in raw if t.get("anchored", True)]
    drags = [t for t in raw if t.get("action") == "drag" and t.get("to")]
    if not samples and not drags:
        return [], 0   # 没有 anchored 目标也没有拖放（如全在托盘里）就不判
    bad = []; bad_to = []
    if layout["type"] == "slots":
        slots = [(*to_px(s["x"], s["y"]), s["r"] * img_px_w) for s in layout["slots"]]
        def nearest(x, y): return min(((math.hypot(x - sx, y - sy), sr) for sx, sy, sr in slots), key=lambda z: z[0])
        for t in samples:
            d, r = nearest(t["x"], t["y"])
            if d > r * (1 + rl["slot_tolerance_ratio"]):
                sx, sy, _ = min(slots, key=lambda z: math.hypot(t["x"] - z[0], t["y"] - z[1]))
                bad.append(f"{t['kind']}(action={t.get('action')},id={t.get('id')})@({t['x']:.0f},{t['y']:.0f}) 离最近锚点({sx:.0f},{sy:.0f}) {d:.0f}px > 允许 {r*(1+rl['slot_tolerance_ratio']):.0f}px，偏移 dx={t['x']-sx:+.0f} dy={t['y']-sy:+.0f}")
        for t in drags:
            d, r = nearest(t["to"]["x"], t["to"]["y"])
            if d > r * (1 + rl["slot_tolerance_ratio"]):
                bad_to.append(f"{t['kind']} 声明的拖放目的地 ({t['to']['x']:.0f},{t['to']['y']:.0f}) 离最近锚点 {d:.0f}px，不是一个锚点")
    else:
        pts = [to_px(p["x"], p["y"]) for p in layout["points"]]
        tol = rl["path_tolerance_ratio"] * rect["h"]
        for t in samples:
            cands = [_pt_seg(t["x"], t["y"], pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
            inside = [c for c in cands if c[0]]                      # 优先取 x 落在线段范围内的
            dy = min((c[1] for c in (inside or cands)), key=abs)      # 再取竖向偏差最小的
            # 允许物件中心在路径上方（底边贴线）最多 0.8 个物件高，下方最多 tol
            if dy > tol or dy < -(t["h"] * 0.8 + tol):
                bad.append(f"{t['kind']}@({t['x']:.0f},{t['y']:.0f}) 偏离轨道 {dy:.0f}px（允许 -{t['h']*0.8+tol:.0f}~+{tol:.0f}）")
    ratio = len(bad) / len(samples) if samples else 0.0
    fails = [f"物理层：{len(bad)}/{len(samples)} 个目标采样悬空/偏离锚点（允许 10%）。例：{bad[0]}"
             + "。修法：格子里的物件一律 rt.placeInSlot(sp, slot, k)（中心=锚点中心略上 0.12r），不要自己算偏移；托盘/手里的物件在 targets 里标 anchored:false"] if ratio > 0.10 else []
    if ratio > 0.10: fails.append("物理层样本：" + " | ".join(bad[:4]))
    if drags and len(bad_to) / len(drags) > 0.10:
        fails.append(f"物理层：{len(bad_to)}/{len(drags)} 个拖放目的地不在锚点上。例：{bad_to[0]}")
    return fails, ratio


def _pt_seg(px, py, a, b):
    """返回 (水平投影是否在段内, 竖向偏差 dy=py-线上y)；只在 x 落在段内时用竖向偏差，否则用端点距离"""
    (ax, ay), (bx, by) = a, b
    if bx == ax: return (True, py - ay)
    t = (px - ax) / (bx - ax)
    if t < 0 or t > 1:
        ex, ey = (ax, ay) if t < 0 else (bx, by)
        return (False, math.copysign(math.hypot(px - ex, py - ey), py - ey))
    return (True, py - (ay + t * (by - ay)))


# ---------------- 浏览器层 + 可玩通层 ----------------
def render_checks(page, rules_r, rect, W, H, out_dir, vpname):
    """状态说有目标 → 屏幕对应位置必须真的画了东西，而且画面变化的大头必须发生在目标声称的位置。
    做法：隐藏 #overlay，取 menu 基准帧；进入 playing 后每次采样先 setTimeScale(0) 冻结，再同时取截图与 state；
    逐目标看局部像素差（幽灵），再看目标框内的变化能量占整个 stage 变化能量的比例（错位）。"""
    from PIL import Image, ImageChops, ImageStat
    page.add_style_tag(content="#overlay,#bf-hint,.bf-praise,.bf-glow,.bf-spark{display:none!important}")
    page.evaluate("() => { window.__bf.setTimeScale(1); window.__bf.reset(9); }")
    page.wait_for_timeout(300)
    base = Image.open(io.BytesIO(page.screenshot())).convert("L")
    page.evaluate("() => window.__bf.start()")
    page.wait_for_timeout(700)
    # 教学课：目标只在该步的有效窗口内出现（如火候到 62% 才能翻面），先 4 倍速快进直到出现第一个 target（最多 40 秒游戏时间）
    if not page.evaluate("() => (window.__bf.state().targets || []).length"):
        page.evaluate("() => window.__bf.setTimeScale(4)")
        for _ in range(40):
            page.wait_for_timeout(250)
            if page.evaluate("() => (window.__bf.state().targets || []).length"): break
        page.evaluate("() => window.__bf.setTimeScale(1)")
    samples, ghosts, outside, ratios = [], [], [], []; saw_static = False
    sx = None
    for i in range(rules_r["samples"]):
        page.evaluate("() => window.__bf.setTimeScale(0)")
        page.wait_for_timeout(80)                      # 等最后一帧渲染完
        st = page.evaluate("() => window.__bf.state()")
        shot = Image.open(io.BytesIO(page.screenshot())).convert("L")
        page.evaluate("() => window.__bf.setTimeScale(1)")
        sx = shot.width / W
        if st["targets"]:
            diff = ImageChops.difference(shot, base)
            if rect:
                stage_box = tuple(int(v * sx) for v in (rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["h"]))
                e_total = sum(diff.crop(stage_box).tobytes())
            else:
                e_total = sum(diff.tobytes())
            mask = Image.new("L", diff.size, 0)
            from PIL import ImageDraw
            md = ImageDraw.Draw(mask)
            for tg in st["targets"]:
                if tg.get("static"): saw_static = True; continue   # 静态目标（照片里的备料）：本来就没有像素变化，不做幽灵检查
                samples.append(tg)
                if rect and not (rect["x"] <= tg["x"] <= rect["x"] + rect["w"] and rect["y"] <= tg["y"] <= rect["y"] + rect["h"]):
                    outside.append(tg); continue
                hw, hh = max(10, tg["w"] * 0.65), max(10, tg["h"] * 0.65)     # 框放大 30% 容纳光斑/阴影
                box = tuple(int(v * sx) for v in (max(0, tg["x"] - hw), max(0, tg["y"] - hh), min(W, tg["x"] + hw), min(H, tg["y"] + hh)))
                if box[2] - box[0] < 4 or box[3] - box[1] < 4: outside.append(tg); continue
                md.rectangle(box, fill=255)
                # 局部判定：框内"明显变化"像素（差值>20）的占比，比均值更抗小物件/大框稀释
                hist = diff.crop(box).histogram()
                local = 100.0 * sum(hist[20:]) / max(1, sum(hist))
                if local < rules_r.get("min_changed_pct", 2.0):
                    ghosts.append((tg, round(local, 1)))
                    if len(ghosts) == 1: shot.save(out_dir / f"{vpname}-ghost.png")
            e_in = sum(ImageChops.multiply(diff, mask).tobytes()) / 1.0
            if e_total > 0: ratios.append(e_in / e_total)
        page.wait_for_timeout(rules_r["interval_ms"])
    fails = []
    if not samples and not saw_static:
        fails.append("渲染检查期间没有出现任何 target（应有目标）")
    if samples and len(outside) / len(samples) > 0.3:   # 允许少量目标在屏幕外（如从屏幕下方抛出的瞬间）
        o = outside[0]; fails.append(f"{len(outside)}/{len(samples)} 个目标越出 stage，例 {o['kind']}@({o['x']:.0f},{o['y']:.0f})")
    if samples and len(ghosts) / max(1, len(samples)) > 0.2:
        g, d = ghosts[0]
        fails.append(f"渲染与状态不一致：{len(ghosts)}/{len(samples)} 个目标在 state 里有、屏幕对应位置却没画东西（变化像素占比 {d}%<{rules_r.get('min_changed_pct', 2.0)}%），例 {g['kind']}@({g['x']:.0f},{g['y']:.0f})")
    med = sorted(ratios)[len(ratios) // 2] if ratios else None
    # 变化集中度只做参考不判 FAIL：满盘烤制/多物件动画时目标框外变化天然多（bbq 5%、takoyaki 20%），幽灵检查（目标处没画东西）才是错位的判据
    if med is not None and med < rules_r.get("min_energy_ratio", 0.15) and not ghosts:
        print(f"    ⓘ 变化集中度 {med:.0%} 偏低（参考值，不判失败；目标处均有绘制）")
    return fails, len(samples), len(ghosts), med


def lesson_edge_probes(page, max_startup_ms):
    """教学课边界输入（此前只试过"按 targets 做对的事"）：
    ① 中断恢复：开局后中途刷新页面，必须在启动时限内重新就绪并能再开局；
    ② 非法/顺序颠倒输入：把不是当前步要的备料拖进锅，不许报错、不许把这一步算过（引擎该"回位并提示这步还不用它"）。"""
    fails, info = [], {}
    page.evaluate("() => { window.__bf.setTimeScale(1); window.__bf.reset(3); window.__bf.start(); }"); page.wait_for_timeout(1200)
    t0 = time.time()
    try:
        page.reload(); page.wait_for_function("() => window.__bf && window.__bf.ready", timeout=max_startup_ms + 2000)
        info["reload_ready_ms"] = int((time.time() - t0) * 1000)
        page.evaluate("() => window.__bf.start()"); page.wait_for_timeout(600)
        ph = page.evaluate("() => window.__bf.state().phase")
        if ph != "playing": fails.append(f"中途刷新后重新开局失败（phase={ph}）")
    except Exception as e:
        fails.append(f"中途刷新后 {max_startup_ms}ms 内 __bf.ready 未就绪（中断恢复失败）: {str(e)[:60]}"); return fails, info
    page.evaluate("() => window.__bf.setTimeScale(4)"); s = None
    for _ in range(100):
        s = page.evaluate("() => window.__bf.state()")
        if s["phase"] == "over" or any(t.get("action") == "drag" and t.get("to") and not str(t.get("kind", "")).startswith("ui:") for t in s["targets"]): break
        page.wait_for_timeout(80)
    page.evaluate("() => window.__bf.setTimeScale(1)")
    drag = next((t for t in s["targets"] if t.get("action") == "drag" and t.get("to") and not str(t.get("kind", "")).startswith("ui:")), None) if s else None
    if not drag: info["wrong_ingredient"] = "没等到备料拖拽步，跳过"; return fails, info
    pantry = page.evaluate("""() => { const L=(window.BF_ASSETS||{}).__layout; if(!L||!L.pantry) return []; const st=document.getElementById('stage').getBoundingClientRect(); const W=st.width,H=st.height;
        const sc=Math.max(W/L.img_w,H/L.img_h), ox=(W-L.img_w*sc)/2, oy=(H-L.img_h*sc)/2; return L.pantry.map(p=>({name:p.name, x:st.left+ox+p.x*L.img_w*sc, y:st.top+oy+p.y*L.img_h*sc})); }""")
    if not pantry:   # 贴纸模式没有布局锚点：按引擎的兜底备料列公式（x=0.85·SW，台面区等距）+ game.js 里的 LESSON.pantry 顺序推算各件位置
        names = []
        try:
            src = (Path(page.url.split("/games/")[0]) if False else None)  # noqa: 占位，保持行数
            gj = next((p for p in [Path(__file__).resolve().parent.parent / "games" / page.url.split("/games/")[1].split("/")[0] / "game.js"] if p.exists()), None)
            if gj:
                m = re.search(r'"pantry":\s*\[(.*?)\]', gj.read_text(encoding="utf-8"), re.S)
                if m: names = re.findall(r'"([^"]+)"', m.group(1))
        except Exception: names = []
        if names:
            pantry = page.evaluate("""(names) => { const st=document.getElementById('stage').getBoundingClientRect(); const SW=st.width,SH=st.height; const L=(window.BF_ASSETS||{}).__layout||{};
                const iw=L.img_w||9, ih=L.img_h||16, s=Math.max(SW/iw,SH/ih), h=ih*s; const cover=(ny)=>(SH-h)/2+ny*h;
                const yTop = L.counter_top ? Math.min(0.5, cover(L.counter_top)/SH+0.08) : 0.22; const n=names.length;
                return names.map((name,k)=>({name, x: st.left+SW*0.85, y: st.top+SH*(n===1?0.55:yTop+(0.86-yTop)*k/(n-1))})); }""", names)
            info["pantry_source"] = "engine-formula"
    wrong = next((o for o in pantry if o["name"] != drag["kind"] and math.hypot(o["x"] - drag["x"], o["y"] - drag["y"]) > 30), None)
    if not wrong: info["wrong_ingredient"] = "布局里没有别的备料可拿错，跳过"; return fails, info
    try:   # 候选位置得真的画着东西（否则探针是空转的）：看 60px 方块内像素是否有起伏
        from PIL import Image, ImageStat
        im = Image.open(io.BytesIO(page.screenshot())).convert("L"); R = 30
        std = ImageStat.Stat(im.crop((int(wrong["x"] - R), int(wrong["y"] - R), int(wrong["x"] + R), int(wrong["y"] + R)))).stddev[0]
        info["wrong_candidate_pixels_std"] = round(std, 1)
        if std < 6: info["wrong_ingredient_note"] = f"候选位置（{wrong['name']}）几乎没画东西（像素起伏 {std:.1f}），这次拿错探针可能空转"
    except Exception: pass
    snap = "() => { const s=window.__bf.state(); return {step: s.lesson.step, results: JSON.stringify(s.lesson.results), errs: (window.__bf.errors||[]).length, phase: s.phase}; }"
    before = page.evaluate(snap)
    bot.do_action(page, {"action": "drag", "x": wrong["x"], "y": wrong["y"], "to": drag["to"]}); page.wait_for_timeout(700)
    after = page.evaluate(snap)
    info["wrong_ingredient"] = {"dragged": wrong["name"], "expected": drag["kind"], "before": before, "after": after}
    if after["step"] != before["step"] or after["results"] != before["results"]:
        fails.append(f"拿错食材（{wrong['name']}，这步要的是 {drag['kind']}）拖进锅也把这一步算过了（step {before['step']}→{after['step']}）：非法输入未被拒")
    if after["errs"] > before["errs"]: fails.append(f"拿错食材拖进锅触发了 __bf.errors（{after['errs'] - before['errs']} 条）")
    return fails, info


def browser_and_bot(url, rules, game_dir, out_dir: Path, report):
    from playwright.sync_api import sync_playwright
    rules_b, rules_bot, rs, rl, rr = rules["browser"], rules["bot"], rules["stage"], rules["layout"], rules["render"]
    layout_path = game_dir / rl["file"]
    layout = json.loads(layout_path.read_text(encoding="utf-8")) if layout_path.exists() else None
    fails = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        for vp in rules_b["viewports"]:
            primary = vp.get("primary", False)
            vpr = {"name": vp["name"], "console_errors": [], "page_errors": [], "failed_requests": [], "screens": [], "games": []}
            report["viewports"].append(vpr)
            ctx = browser.new_context(viewport={"width": vp["w"], "height": vp["h"]}, device_scale_factor=1)
            if vp.get("fake_dpr", 1) != 1:   # 无头下 dsf>1 截不到 WebGL，改为伪装 devicePixelRatio 逼出像素密度 bug
                ctx.add_init_script(f"Object.defineProperty(window,'devicePixelRatio',{{get:()=>{vp['fake_dpr']}}});")
            page = ctx.new_page()
            page.on("console", lambda m: vpr["console_errors"].append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: vpr["page_errors"].append(str(e)))
            page.on("requestfailed", lambda r: vpr["failed_requests"].append(f"{r.url} {r.failure}"))
            page.on("response", lambda r: vpr["failed_requests"].append(f"{r.url} HTTP {r.status}") if r.status >= 400 else None)

            t0 = time.time()
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_function("() => window.__bf && window.__bf.ready === true", timeout=rules_b["max_startup_ms"] + 2000)
                vpr["startup_ms"] = int((time.time() - t0) * 1000)
                if vpr["startup_ms"] > rules_b["max_startup_ms"]:
                    fails.append(f"[{vp['name']}] 启动 {vpr['startup_ms']}ms 超过 {rules_b['max_startup_ms']}ms")
            except Exception:
                vpr["startup_ms"] = None
                fails.append(f"[{vp['name']}] {rules_b['max_startup_ms']}ms 内 __bf.ready 未就绪")
                shot = out_dir / f"{vp['name']}-not-ready.png"; page.screenshot(path=str(shot)); vpr["screens"].append(shot.name)
                ctx.close(); continue

            ver = page.evaluate("() => window.__bf.version")
            if ver != 1: fails.append(f"[{vp['name']}] __bf.version={ver}，期望 1")
            W, H = vp["w"], vp["h"]
            rect = stage_rect(page, rs["selector"]); vpr["stage"] = rect
            fails += [f"[{vp['name']}] {x}" for x in stage_checks(rect, rs, W, H)]
            cv = page.evaluate("() => { const c = document.querySelector('canvas'); if (!c) return null; const b = c.getBoundingClientRect(); return {x: b.x, y: b.y, w: b.width, h: b.height, bw: c.width, bh: c.height}; }")
            vpr["canvas"] = cv
            if not cv:
                fails.append(f"[{vp['name']}] 没有 canvas")
            elif rect and (abs(cv["w"] - rect["w"]) > 2 or abs(cv["h"] - rect["h"]) > 2 or abs(cv["x"] - rect["x"]) > 2 or abs(cv["y"] - rect["y"]) > 2):
                fails.append(f"[{vp['name']}] canvas 的 CSS 尺寸/位置 ({cv['x']:.0f},{cv['y']:.0f} {cv['w']:.0f}x{cv['h']:.0f}) ≠ stage ({rect['x']:.0f},{rect['y']:.0f} {rect['w']:.0f}x{rect['h']:.0f})；devicePixelRatio={vp.get('fake_dpr',1)} 下 setSize/setPixelRatio 用错，画面会被放大裁切或错位")

            shot = out_dir / f"{vp['name']}-menu.png"; page.screenshot(path=str(shot)); vpr["screens"].append(shot.name)

            is_lesson = bool(page.evaluate("() => !!(window.__bf.state().lesson)"))
            if primary:
                games = []; bot.TRACE.clear()
                ts_goal = 10 ** 9 if is_lesson else rules_bot["target_score"]                  # 教学课：机器人要走完全部步骤，不按分数停手
                wall = rules_bot.get("lesson_max_game_wall_s", 100) if is_lesson else rules_bot["max_game_wall_s"]
                for seed in rules_bot["seeds"]:
                    s, probs = bot.play_one(page, seed, ts_goal, wall, W, H)
                    games.append({"seed": seed, "final": s, "problems": probs})
                    fails += [f"[{vp['name']}] seed={seed}: {x}" for x in probs]
                    if seed == rules_bot["seeds"][0]:
                        shot = out_dir / f"{vp['name']}-over.png"; page.screenshot(path=str(shot)); vpr["screens"].append(shot.name)
                vpr["games"] = games
                les = games[0]["final"].get("lesson") if games else None
                if les is not None:
                    vpr["lesson"] = les
                    done = len([x for x in (les.get("results") or []) if x is not None])
                    if done < les.get("total", 0): fails.append(f"[{vp['name']}] 教学课：机器人只完成 {done}/{les.get('total')} 步（每步必须能被 targets 引导完成）")
                    zeros = [i + 1 for i, x in enumerate(les.get("results") or []) if x == 0]   # 超时得 0 也会"完成"：步骤要的食材/目标从没出现过（突变体 lesson-ghost-ingredient 曾借此逃掉）
                    if zeros: fails.append(f"[{vp['name']}] 教学课：第 {zeros} 步机器人得 0 分——该步没出现过可执行目标或判定不可达（按目标出手的机器人不该得 0）")
                    if les.get("verdicts", 0) < les.get("total", 0): fails.append(f"[{vp['name']}] 教学课：只出现 {les.get('verdicts',0)} 次对错反馈，应每步 1 次")
                    if any(g["final"]["lives"] < g["final"].get("lives", 3) for g in games) or any(("lives" in g["final"] and g["final"]["lives"] <= 0) for g in games):
                        fails.append(f"[{vp['name']}] 教学课不允许命数归零结束")
                hb = rules_bot.get("human")
                if hb:
                    hs, hp = bot.play_human(page, 21, hb["target_score"], hb["min_survive_s"], hb["reaction_ms"], hb["action_interval_ms"], W, H)
                    vpr["human"] = {"final": hs, "problems": hp}
                    if hs.get("lesson") is not None:      # 教学课：慢手不看分数/存活，看星级
                        hp = [x for x in hp if "只得" not in x and "就输了" not in x]
                        if (hs["lesson"].get("stars") or 0) < 2: hp.append(f"教学课：慢手机器人只拿到 {hs['lesson'].get('stars')} 星（平均准确度 {hs['lesson'].get('avg')}），要求 ≥2 星：窗口太短或判定太严，普通人学不会")
                    fails += [f"[{vp['name']}] {x}" for x in hp]
                # 新手引导与情绪反馈（运行时游戏 state().ui 可读；老游戏无 ui 字段则不判）
                ui = games[0]["final"].get("ui") if games else None
                if ui is not None:
                    vpr["ui"] = ui
                    if ui.get("hintsShown", 0) < 1: fails.append(f"[{vp['name']}] 首局没有出现任何新手引导（hintsShown=0）：玩家不知道该点/拖/滑哪里")
                    if games[0]["final"].get("lesson") is None and games[0]["final"]["score"] >= rules_bot["target_score"] and ui.get("praisesShown", 0) < 1:   # 教学课的情绪反馈由每步判定（verdicts）保证
                        fails.append(f"[{vp['name']}] 机器人得了 {games[0]['final']['score']} 分却没有任何情绪反馈（praisesShown=0）：连击赞美/大字/粒子缺失")
                scored = sum(1 for g in games if g["final"]["score"] > 0 and g["final"]["phase"] == "over")
                if scored < rules_bot["min_games_with_score"]:
                    fails.append(f"[{vp['name']}] 只有 {scored} 局得分并结束，要求 ≥{rules_bot['min_games_with_score']}")
                if is_lesson:   # 边界输入：中断恢复 + 拿错食材（只试正常输入的绿灯不算绿灯）
                    ef, einfo = lesson_edge_probes(page, rules_b["max_startup_ms"]); vpr["edge"] = einfo
                    fails += [f"[{vp['name']}] {x}" for x in ef]

            # 游玩中截图
            page.evaluate("() => { window.__bf.setTimeScale(1); window.__bf.reset(7); window.__bf.start(); }")
            page.wait_for_timeout(1300)
            shot = out_dir / f"{vp['name']}-playing.png"; page.screenshot(path=str(shot)); vpr["screens"].append(shot.name)
            # 素材一致性：注入了素材时，target.kind 必须是 BF_ASSETS 的键，否则物件只能是占位色块
            keys = page.evaluate("() => Object.keys(window.BF_ASSETS || {}).filter(k => !k.startsWith('__'))")
            if keys and primary:
                st0 = page.evaluate("() => window.__bf.state()")
                seen_targets = list(st0["targets"]) + list(bot.TRACE)   # 教学课开局那一刻常常还没有 target（目标只在有效窗口出现），只看开局等于没查：把机器人全程见过的目标都算上（突变体 lesson-ghost-ingredient 曾借此逃掉）
                unknown = sorted({t["kind"] for t in seen_targets if t["kind"] not in keys and not str(t["kind"]).startswith("ui:")})   # ui: 前缀 = 界面控件（火力档），不是素材
                if unknown:
                    fails.append(f"[{vp['name']}] 目标 kind {unknown} 不在 BF_ASSETS 键 {keys[:6]}… 里，画出来只能是占位色块（PRD 物件名与代码不一致）")

            # 所有视口：目标在 stage 内 + 屏幕上真的画了 + 落在布局锚点上
            rf, ns, ng, er = render_checks(page, rr, rect, W, H, out_dir, vp["name"]); vpr["render"] = {"samples": ns, "ghosts": ng, "energy_ratio": er}
            fails += [f"[{vp['name']}] {x}" for x in rf]
            if layout and rect:
                lf, ratio = layout_checks(page, layout, rl, rect, extra_samples=(bot.TRACE if primary else None)); vpr["layout_violation_ratio"] = ratio
                fails += [f"[{vp['name']}] {x}" for x in lf]

            if primary:
                err = bot.idle_run(page, 11, (rules_bot.get("lesson_idle_must_end_sim_s", 90) if is_lesson else rules_bot["idle_must_end_sim_s"]), rules_bot["idle_time_scale"])[1]
                if err: fails.append(f"[{vp['name']}] {err}")
                else:
                    err = bot.determinism(page, 5, (rules_bot.get("lesson_idle_must_end_sim_s", 90) if is_lesson else rules_bot["idle_must_end_sim_s"]), rules_bot["idle_time_scale"])
                    if err: fails.append(f"[{vp['name']}] {err}")

            bf_errors = page.evaluate("() => window.__bf.errors || []")
            if bf_errors: fails.append(f"[{vp['name']}] __bf.errors 非空: {bf_errors[:3]}")
            if len(vpr["console_errors"]) > rules_b["console_errors_allowed"]:
                fails.append(f"[{vp['name']}] console.error {len(vpr['console_errors'])} 条: {vpr['console_errors'][:2]}")
            if len(vpr["page_errors"]) > rules_b["page_errors_allowed"]:
                fails.append(f"[{vp['name']}] 未捕获异常 {len(vpr['page_errors'])} 条: {vpr['page_errors'][:2]}")
            if len(vpr["failed_requests"]) > rules_b["failed_requests_allowed"]:
                fails.append(f"[{vp['name']}] 失败请求 {len(vpr['failed_requests'])} 条: {vpr['failed_requests'][:2]}")
            ctx.close()
        browser.close()
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_dir")
    ap.add_argument("--rules", default=str(ROOT / "specs/rules/h5-hard-rules.json"))
    ap.add_argument("--out", default=str(ROOT / "reports"))
    ap.add_argument("--serve-root", default=str(ROOT))
    a = ap.parse_args()

    game_dir = Path(a.game_dir).resolve(); serve_root = Path(a.serve_root).resolve()
    rules = json.loads(Path(a.rules).read_text(encoding="utf-8"))
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(a.out) / f"{game_dir.name}-{ts}"; out_dir.mkdir(parents=True, exist_ok=True)
    report = {"game": str(game_dir), "rules": rules["id"], "ts": ts, "static": {}, "viewports": [], "fails": []}

    fails, info = static_checks(game_dir, rules["static"])
    report["static"] = {"info": info, "fails": fails}
    all_fails = list(fails)
    if not fails or all(("禁用模式" in f or "非相对" in f or "缺少必需内容" in f) for f in fails):
        try:
            rel = game_dir.relative_to(serve_root)
        except ValueError:
            print("game_dir 必须在 serve-root 之下", file=sys.stderr); sys.exit(2)
        port = free_port(); httpd = serve(serve_root, port)
        url = f"http://127.0.0.1:{port}/{rel.as_posix()}/index.html"
        try:
            all_fails += browser_and_bot(url, rules, game_dir, out_dir, report)
        except Exception as e:
            report["verifier_error"] = repr(e)
            (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"检验器自身异常: {e!r}", file=sys.stderr); print("VERDICT: ERROR"); sys.exit(2)
        finally:
            httpd.shutdown()
    else:
        all_fails.append("静态层致命错误，跳过浏览器层")

    report["fails"] = all_fails
    report["verdict"] = "PASS" if not all_fails else "FAIL"
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    try:   # 轮次台账：每次判官出手都记一行（引擎/工厂指纹 + 裁决），latency.py 靠它算发现延迟与复发
        import ledger; ledger.record(game_dir, "verify", verdict=report["verdict"], fails=all_fails[:12], report=ts)
    except Exception as e:
        print(f"  ⚠ 台账写入失败: {e!r}", file=sys.stderr)
    print(f"报告: {out_dir}")
    for f in all_fails: print("  ✗", f)
    for vp in report["viewports"]:
        gs = vp.get("games", []); st = vp.get("stage") or {}
        hm = vp.get("human", {}).get("final")
        print(f"  [{vp['name']}] 启动 {vp.get('startup_ms')}ms · stage {st.get('w', 0):.0f}x{st.get('h', 0):.0f} · 局分 {[g['final']['score'] for g in gs]}"
              + (f" · 慢手 {hm['score']}分/{hm['t']:.0f}s" if hm else "")
              + (f" · 悬空率 {vp['layout_violation_ratio']:.0%}" if "layout_violation_ratio" in vp else "")
              + (f" · 幽灵 {vp['render']['ghosts']}/{vp['render']['samples']} · 变化集中度 {(vp['render']['energy_ratio'] or 0):.0%}" if "render" in vp else ""))
    print(f"VERDICT: {report['verdict']}")
    sys.exit(0 if not all_fails else 1)


if __name__ == "__main__":
    main()
