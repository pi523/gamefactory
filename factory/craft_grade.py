#!/usr/bin/env python3
"""手作模拟品类盲测打分：把 game-sushi（老板认可的参考）与候选游戏各驾驭一遍截图，随机贴 A/B 标签，
交给两家**非 Anthropic** 的看图模型（默认 openai/gpt-5.4 主判 + google/gemini-3.1-pro-preview 复核）按宏观维度打 1–10 分。
判据（以两两比较为主，绝对分噪声太大）：每个维度"候选比参考好多少"的均值 ≥ −0.5（不比参考差），材质绝对均值 ≥ 4.5，穿模 0 → GRADE: PASS。
用法: .venv/bin/python factory/craft_grade.py [--cand game-drink] [--ref game-sushi] [--judges openai/gpt-5.4,google/gemini-3.1-pro-preview] [--shots-only]
产物: <cand>/grade/<ts>/*.png（截图）、<cand>/grade-latest.json、grade-latest.md、grade-log.jsonl
"""
import argparse, http.server, json, random, socket, socketserver, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402

DIMS = [("gameplay", "玩法清晰度：一眼看懂现在该做什么（选什么、对哪里做什么）、下一步是什么，操作是否与现实动作同构。注意：手作模拟按行业惯例不告诉玩家加多少（订单只写要什么，比例/分量是隐形评分，结算才揭示），界面没有目标线/刻度不算扣分"),
        ("achievement", "成就感/成品可回溯：成品是否明显是玩家操作的结果（而不是预置贴图），过程有没有一个真的物理/几何关系撑住"),
        ("share", "分享欲：结算画面是否值得截图发给朋友 —— 成品 + 评级 + 分维度 + 一句人话点评是否同屏且好看"),
        ("polish", "完成度/UI：信息层级、订单/进度/操作三处 UI 是否清楚、有撤销/仪表/提示、没有断头路"),
        ("visuals", "画面：布光（冷暖层次、软阴影、反射）、材质、构图、整体真实感与氛围"),
        ("camera", "镜头感：机位是否贴着当前动作（而不是围着场景转）、过渡帧是否平稳有电影感、竖屏构图是否完整"),
        ("animation", "动画感：从中间帧判断运动是否有弧线/错峰/柔和缓动、有没有'活着'的待机细节"),
        ("material", "主体材质真实感：这款游戏的核心材质（米饭/海苔/或液体/玻璃/冰）看起来像不像真的")]

PROMPT = """你是独立游戏评审，专审"手作模拟"小游戏（玩家按工序做出一件成品然后被打分）。下面是两款游戏 A 和 B 的实机截图（手机竖屏，按工序顺序，含镜头过渡中间帧与结算画面），每张图前有标签。
你不知道哪一款是参考、哪一款是候选 —— 请独立、严格、按同一把尺子给两款各打分。不要客气：占位色块、悬空物件、**穿模（物体互相穿插、装饰穿过杯壁）**、模糊材质、UI 挡住主体、镜头切得生硬、结算画面看不到成品，都要扣。

评分维度（每项 1–10，10 = 商业上架水准）：
{dims}

只输出一个 JSON 对象，**必须同时包含 A 和 B 两款**，结构：
{{"games": [
   {{"tag": "A", "what": "一句话描述 A 是什么游戏、几道工序", "scores": {{{keys}}}, "notes": {{{keys}}}}},
   {{"tag": "B", "what": "...", "scores": {{...}}, "notes": {{...}}}}
 ],
 "compare": {{{cmpkeys}}},
 "verdict": "一句话：哪一款更像成品、差在哪",
 "fixes": [{{"game": "A|B", "dim": "维度键", "fix": "具体可执行的改法（说清改哪个画面的哪个元素、改成什么样）"}}]}}
compare 每个维度一个数：**B 比 A 好多少**，取 -3（A 明显好）… 0（差不多）… +3（B 明显好）的整数，这是最重要的输出，请仔细比对同工序的两张图再定。
notes 每条一句话说明扣分点；fixes 只给分数较低那款、最多 8 条、按收益排序。games 数组长度必须为 2。"""


RAW_DIR = None


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def serve():
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), lambda *a, **k: Quiet(*a, directory=str(ROOT), **k)); httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


# ---------------- 驾驭：寿司（参考） ----------------
def capture_sushi(pg, port, out: Path):
    shots = []
    def shot(label, name): p = out / f"sushi-{name}.png"; pg.screenshot(path=str(p)); shots.append((label, p))
    pg.route("**/three@0.169.0/build/three.module.js", lambda r: r.fulfill(path=str(ROOT / "vendor/three.module.js"), content_type="application/javascript"))
    pg.goto(f"http://127.0.0.1:{port}/game-sushi/index.html"); pg.wait_for_function("() => window.__game && window.__world", timeout=20000); pg.wait_for_timeout(1200)
    shot("工序 1 开始（铺饭）", "01-step1")
    pg.evaluate("""() => { const g = window.__game; for (let i = 0; i < 1400; i++) g.roll.addRice(-4 + Math.random() * 6.6, (Math.random() - 0.5) * 6.4); g.updateMeter(); }""")
    pg.wait_for_timeout(300); shot("工序 1 进行中（米饭铺到约 85%）", "02-step1-mid")
    pg.evaluate("() => window.__game.onNext()"); pg.wait_for_timeout(380); shot("镜头过渡中间帧（工序 1→2）", "03-cam-mid"); pg.wait_for_timeout(700)
    pg.evaluate("""() => { const g = window.__game; const need = g.recipe.need; let x = -2.75; for (const k of need) { const kind = g.roll.constructor && 0; const isBead = ['roe','sesame'].includes(k); if (isBead) { for (let i = 0; i < 18; i++) g.roll.addFilling(k, -2.5 + Math.random() * 0.8, (Math.random() - 0.5) * 6); } else { g.roll.addFilling(k, x, 0); x += 0.34; } } g.refreshOrderChips(); }""")
    pg.wait_for_timeout(400); shot("工序 2 完成（配料摆好）", "04-step2")
    pg.evaluate("() => window.__game.onNext()"); pg.wait_for_timeout(1000)
    for i in range(1, 13):
        pg.evaluate(f"() => {{ const g = window.__game; g.roll.setProgress({i/12:.4f}); g.roll.setMatProgress({i/12:.4f}); document.getElementById('roll-fill').style.width = '{int(i/12*100)}%'; }}"); pg.wait_for_timeout(110)
        if i == 6: shot("工序 3 进行中（卷到一半）", "05-step3-mid")
    pg.evaluate("() => window.__game.beginSealing()"); pg.wait_for_function("() => window.__game.phase === 'cut'", timeout=60000); pg.wait_for_timeout(500); shot("工序 4 开始（切开，刀与参考线）", "06-step4")
    pg.evaluate("""() => { const g = window.__game, n = g.recipe.pieces; const V = window.__world.camera.position.constructor; const r = window.__world.renderer.domElement.getBoundingClientRect();
        for (let i = 1; i < n; i++) { const z = -3.5 + 7 * i / n; const v = new V(0, 0.7, z); v.project(window.__world.camera); g.addCut({ clientX: (v.x + 1) / 2 * r.width + r.left, clientY: (1 - v.y) / 2 * r.height + r.top }); } }""")
    pg.wait_for_timeout(500); shot("工序 4 进行中（下刀位置已标）", "07-step4-mid")
    pg.evaluate("() => window.__game.doSlice()"); pg.wait_for_timeout(650); shot("结尾演出中间帧（装盘飞块）", "08-plating-mid")
    pg.wait_for_function("() => window.__game.phase === 'score'", timeout=60000); pg.wait_for_timeout(500); shot("结算画面", "09-score")
    return shots


# ---------------- 驾驭：饮品（候选）—— 按主题工序表通用驱动 ----------------
CLIPS = []
SHOWCASE = {"bar": "朗姆日出", "teashop": "黑糖珍珠奶茶", "cafe": "经典拿铁", "izakaya": "柠檬沙瓦", "teahouse": "正山小种", "shavedice": "草莓炼乳刨冰", "smoothie": "草莓香蕉果昔"}
PHASE_LABEL = {"solids": "加冰", "leaves": "投茶", "fruits": "放果", "pour": "调配（自由倒入）", "extract": "萃取浓缩", "art": "拉花", "shake": "摇匀", "blend": "打匀", "squeeze": "挤柠檬", "stir": "搅拌", "steep": "看汤色等出汤", "shave": "刨冰", "drizzle": "淋糖浆", "garnish": "装饰", "toppings": "加配料", "pull": "拉茶/抻面（来回拉）", "patrol": "关公巡城（提壶巡三杯）", "dots": "韩信点兵（点滴）", "settle": "看泡沫", "roll": "擀皮", "fill": "放馅", "pleat": "捏褶", "boil": "下锅煮", "top": "浇头", "skewer": "串果", "sugar": "熬糖", "coat": "蘸糖", "spread": "摊面糊", "egg": "打蛋", "flip": "翻面", "sauce": "刷酱", "fold": "折叠", "spin": "转盘", "draw": "画糖（走线）", "stick": "上签", "lift": "起画"}
def capture_drink(pg, port, out: Path, cand, theme="bar", recipe=None):
    shots = []
    def adv(sec): pg.evaluate(f"() => window.__advance({sec})")
    def clip(name):
        c = pg.evaluate("() => (window.__game.checkClipping ? window.__game.checkClipping() : [])")
        if c: CLIPS.append((name, c))
    def shot(label, name, a=0.0):
        if a: adv(a)
        pg.evaluate("() => window.__render()"); p = out / f"{cand}-{name}.png"; pg.screenshot(path=str(p)); shots.append((label, p)); clip(name)
    def run_auto(phase, part):
        pg.evaluate(f"() => window.__game.auto.start('{phase}', '{part}')")
        for _ in range(600):
            if not pg.evaluate("() => window.__game.auto.busy()"): break
            adv(0.1); clip(f"{phase}/{part}")   # 每一步都查穿模（硬性条件），不只查截图帧
    from urllib.parse import quote
    rq = "&recipe=" + quote(recipe or SHOWCASE.get(theme, "")) if (recipe or SHOWCASE.get(theme)) else ""
    pg.goto(f"http://127.0.0.1:{port}/{cand}/index.html?harness=1&theme={theme}{rq}"); pg.wait_for_function("() => window.__game && window.__advance", timeout=20000)
    R = pg.evaluate("() => window.__game.recipe"); phases = pg.evaluate("() => window.__theme.phases"); print(f"  候选配方：{R['name']} · 工序 {phases}")
    n = 0
    for i, ph in enumerate(phases):
        if ph == "serve": break
        n += 1; lab = PHASE_LABEL.get(ph, ph)
        if i == 0: shot(f"工序 {n} 开始（{lab}）", f"{n:02d}a-{ph}", 1.0)
        else: shot(f"镜头过渡中间帧（工序 {n-1}→{n}）", f"{n:02d}0-cam-mid", 0.38); shot(f"工序 {n} 开始（{lab}）", f"{n:02d}a-{ph}", 0.6)
        run_auto(ph, "mid"); shot(f"工序 {n} 进行中（{lab}）", f"{n:02d}b-{ph}-mid", 0.15)
        if len([q for q in phases if q != "serve"]) <= 2:   # 工序少的游戏多截两帧动作，别让判官只看到静帧
            shot(f"工序 {n} 进行中 · 续（{lab}）", f"{n:02d}b2-{ph}-mid2", 0.5); shot(f"工序 {n} 进行中 · 再续（{lab}）", f"{n:02d}b3-{ph}-mid3", 0.5)
        run_auto(ph, "end"); shot(f"工序 {n} 完成（{lab}）", f"{n:02d}c-{ph}-done", 1.0)
        pg.evaluate("() => window.__game.auto.next()")
    shot("结尾演出开始（低机位看成品）", "08a-reveal-start", 0.9)
    shot("结尾演出中间帧（侧视上摇镜头）", "08-reveal-mid", 1.3)
    adv(2.4); pg.wait_for_timeout(700); shot("结算画面", "09-score", 0.4)
    # 参考与候选张数差太多会影响判官比较，最多保留 12 张：优先保留每道工序的"完成"帧与结算
    if len(shots) > 12:
        keep = [s for s in shots if "完成" in s[0] or "结算" in s[0] or "演出" in s[0] or "开始（" in s[0] and s is shots[0]]
        mids = [s for s in shots if s not in keep]
        shots = sorted((keep + mids[: max(0, 12 - len(keep))]), key=lambda s: shots.index(s))
    return shots


def normalize(r):
    """容错：模型可能把 A/B 包一层（{"games":{...}}）、用小写、或写成 "游戏A"。统一成 {"A":..., "B":..., "verdict", "fixes"}"""
    while isinstance(r, list) and r and not any(isinstance(x, dict) and "tag" in x for x in r): r = r[0]   # 有的模型把对象包成数组
    if isinstance(r, list): r = {"games": r}
    if isinstance(r, dict) and isinstance(r.get("games"), list):        # 新结构：games=[{tag,...},{tag,...}]
        gs = {str(g.get("tag", "")).strip().upper()[:1]: g for g in r["games"] if isinstance(g, dict)}
        r = {**{k: v for k, v in r.items() if k != "games"}, **gs}
    if isinstance(r, dict) and "A" not in r and "B" not in r:
        for k, v in list(r.items()):
            if isinstance(v, dict) and any(str(kk).upper().strip().endswith(("A", "B")) for kk in v): r = {**v, **{kk: vv for kk, vv in r.items() if kk != k}}; break
    out = {}
    for k, v in r.items():
        ku = str(k).strip().upper()
        if ku in ("A", "游戏A", "GAME A", "GAME_A", "GAMEA") or ku.endswith(" A") or ku.endswith("_A"): out["A"] = v
        elif ku in ("B", "游戏B", "GAME B", "GAME_B", "GAMEB") or ku.endswith(" B") or ku.endswith("_B"): out["B"] = v
        else: out[k] = v
    for t in ("A", "B"):
        g = out.get(t)
        if not isinstance(g, dict): raise ValueError(f"缺少游戏 {t}：{list(r)[:6]}")
        g.setdefault("scores", {}); g.setdefault("notes", {})
        if isinstance(g["scores"], list): g["scores"] = {str(x.get("dim") or x.get("name") or x.get("key")).lower(): x.get("score", x.get("value")) for x in g["scores"] if isinstance(x, dict)}
        if isinstance(g["notes"], list): g["notes"] = {str(x.get("dim") or x.get("name") or x.get("key")).lower(): x.get("note", x.get("text", "")) for x in g["notes"] if isinstance(x, dict)}
        g["scores"] = {str(k).lower(): float(v) for k, v in g["scores"].items() if v is not None}
    out.setdefault("fixes", []); return out


def grade(shots_a, shots_b, model):
    dims = "\n".join(f"- {k}：{d}" for k, d in DIMS); keys = ", ".join(f'"{k}": n' for k, _ in DIMS); cmpkeys = ", ".join(f'"{k}": -3..3' for k, _ in DIMS)
    content = [{"type": "text", "text": PROMPT.format(dims=dims, keys=keys, cmpkeys=cmpkeys)}]
    for tag, shots in (("A", shots_a), ("B", shots_b)):
        content.append({"type": "text", "text": f"\n===== 游戏 {tag} =====（共 {len(shots)} 张，按工序顺序）"})
        for label, p in shots:
            content.append({"type": "text", "text": f"[{tag}] {label}"}); content.append(llm.image_part(str(p)))
    msgs = [{"role": "user", "content": content}]
    text = llm.chat(msgs, model=model, max_tokens=9000, temperature=0.1, json_mode=True, tag=f"grade:{model.split('/')[-1]}")
    def parse(t):
        t = t.strip()
        if t.startswith("```"): t = t.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(t)
    r = parse(text)
    try:
        return normalize(r)
    except Exception as e:                       # 只回了一款：在同一对话里追问补齐
        if RAW_DIR: (RAW_DIR / f"raw-{model.split('/')[-1]}-1.txt").write_text(text, encoding="utf-8")
        msgs += [{"role": "assistant", "content": text}, {"role": "user", "content": "你只输出了一款游戏。请按同一结构输出完整 JSON：games 数组必须同时包含 tag 为 A 和 B 的两款（A 用你上面的评分原样保留），并给出 verdict 与 fixes。只输出 JSON。"}]
        text2 = llm.chat(msgs, model=model, max_tokens=9000, temperature=0.1, json_mode=True, tag=f"grade:{model.split('/')[-1]}:fix")
        if RAW_DIR: (RAW_DIR / f"raw-{model.split('/')[-1]}-2.txt").write_text(text2, encoding="utf-8")
        return normalize(parse(text2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="drinks/game-drink"); ap.add_argument("--ref", default="game-sushi")
    ap.add_argument("--judges", default="openai/gpt-5.4,google/gemini-3.1-pro-preview")
    ap.add_argument("--repeats", type=int, default=3, help="每个判官独立打几遍（判官有噪声，取均值）"); ap.add_argument("--theme", default="bar"); ap.add_argument("--recipe", default=None, help="固定配方名；默认取主题的展示配方（工序最全的那杯），避免抽到'不加冰'这类看不出工序的单"); ap.add_argument("--shots-only", action="store_true"); ap.add_argument("--min-material", type=float, default=4.5); ap.add_argument("--tol", type=float, default=0.5)
    a = ap.parse_args()
    ts = time.strftime("%Y%m%d-%H%M%S") + "-" + a.theme; cand_dir = ROOT / a.cand; out = cand_dir / "grade" / ts; out.mkdir(parents=True, exist_ok=True)
    global RAW_DIR; RAW_DIR = out
    httpd, port = serve()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        errs = {"ref": [], "cand": []}
        pg = b.new_page(viewport={"width": 390, "height": 844}); pg.set_default_timeout(90000); pg.on("pageerror", lambda e: errs["ref"].append(str(e)))
        ref_shots = capture_sushi(pg, port, out); pg.close()
        pg = b.new_page(viewport={"width": 390, "height": 844}); pg.set_default_timeout(90000); pg.on("pageerror", lambda e: errs["cand"].append(str(e))); pg.on("console", lambda m: errs["cand"].append(m.text) if m.type == "error" else None)
        cand_shots = capture_drink(pg, port, out, a.cand, a.theme, a.recipe); pg.close(); b.close()
    httpd.shutdown()
    print(f"截图：参考 {len(ref_shots)} 张 · 候选 {len(cand_shots)} 张 → {out.relative_to(ROOT)}")
    if errs["cand"]: print("  候选运行错误：", errs["cand"][:3])
    nclip = sum(len(c) for _, c in CLIPS)
    print(f"  穿模检查：{nclip} 处" + ("" if not nclip else " → " + "; ".join(f"{n}: {c[0]}" for n, c in CLIPS[:4])))
    if a.shots_only: return
    swap = random.random() < 0.5                       # 盲测：随机谁是 A
    A, B = (cand_shots, ref_shots) if swap else (ref_shots, cand_shots)
    results = {}
    for model0 in a.judges.split(","):
        for rep in range(1, a.repeats + 1):
            base = model0.strip(); model = base if a.repeats == 1 else f"{base}#{rep}"; t0 = time.time(); r = None
            try:
                for attempt in (1, 2):                       # 偶发只回一款/格式跑偏：重试一次
                    try: r = grade(A, B, base); break
                    except Exception as e:
                        if attempt == 2: raise
                        print(f"  ⚠ {model} 第 1 次输出不完整（{str(e)[:60]}），重试")
                cand_tag, ref_tag = ("A", "B") if swap else ("B", "A")
                cmp = r.get("compare") or {}; sign = 1 if cand_tag == "B" else -1          # compare = B 比 A 好多少
                margin = {str(k).lower(): sign * float(v) for k, v in cmp.items() if v is not None}
                results[model] = {"cand": r[cand_tag], "ref": r[ref_tag], "margin": margin, "verdict": r.get("verdict"), "fixes": [f for f in r.get("fixes", []) if str(f.get("game", "")).upper().startswith(cand_tag)], "secs": round(time.time() - t0)}
                print(f"  {model}: {results[model]['secs']}s")
            except Exception as e:
                print(f"  ✗ {model} 打分失败: {str(e)[:200]}")
                (out / f"bad-{model.split('/')[-1].replace('#', '-')}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1) if r else str(e), encoding="utf-8")
    if not results: print("GRADE: ERROR"); sys.exit(2)
    # 汇总
    rows = []; ok = True
    for k, _ in DIMS:
        cs = [results[m]["cand"]["scores"].get(k) for m in results]; rs = [results[m]["ref"]["scores"].get(k) for m in results]
        ms = [results[m]["margin"].get(k) for m in results if results[m]["margin"].get(k) is not None]
        cm = sum(cs) / len(cs); rm = sum(rs) / len(rs); mm = sum(ms) / len(ms) if ms else (cm - rm)
        # 判据以两两比较为主（绝对分噪声太大）：候选不比参考差（pairwise 均值 ≥ −0.5）；材质另加绝对下限
        passed = mm >= -a.tol and (k != "material" or cm >= a.min_material)
        ok &= passed; rows.append((k, cm, rm, cs, rs, passed, mm, ms))
    md = [f"# 盲测打分 {ts}", f"参考 {a.ref} · 候选 {a.cand} · 判官 {', '.join(results)} · 候选标签 {'A' if swap else 'B'}", "",
          "| 维度 | 候选(均) | 参考(均) | 两两比较(候选−参考,均) | 各判 | 过 |", "|---|---|---|---|---|---|"]
    for k, cm, rm, cs, rs, passed, mm, ms in rows: md.append(f"| {k} | {cm:.1f} | {rm:.1f} | {mm:+.2f} | {[int(x) for x in ms]} | {'✓' if passed else '✗'} |")
    md.append("")
    for m, r in results.items():
        md += [f"## {m}", f"- 候选：{r['cand'].get('what')}", f"- 参考：{r['ref'].get('what')}", f"- 裁决：{r.get('verdict')}", "- 候选扣分点："]
        md += [f"  - {k}: {r['cand'].get('notes', {}).get(k, '')}" for k, _ in DIMS]
        md += ["- 改法（候选）："] + [f"  - [{f.get('dim')}] {f.get('fix')}" for f in r["fixes"]] + [""]
    if nclip: ok = False; md.append(f"穿模检查：{nclip} 处违规（硬性条件）" + "".join(f"\n- {n}: {c}" for n, c in CLIPS))
    else: md.append("穿模检查：0 处")
    verdict = "PASS" if ok else "FAIL"; md.append(f"GRADE: {verdict}")
    (cand_dir / f"grade-latest-{a.theme}.md").write_text("\n".join(md), encoding="utf-8")
    (cand_dir / f"grade-latest-{a.theme}.json").write_text(json.dumps({"ts": ts, "swap": swap, "results": results, "rows": [r[:6] + (r[6],) for r in rows], "verdict": verdict}, ensure_ascii=False, indent=1), encoding="utf-8")
    (cand_dir / "grade-log.jsonl").open("a", encoding="utf-8").write(json.dumps({"ts": ts, "theme": a.theme, "clipping": nclip, "verdict": verdict, "rows": [(k, round(cm, 2), round(rm, 2), round(mm, 2)) for k, cm, rm, cs, rs, passed, mm, ms in rows]}, ensure_ascii=False) + "\n")
    print("\n".join(md[3:3 + 2 + len(rows)]))
    for m, r in results.items():
        print(f"\n[{m}] {r.get('verdict')}")
        for f in r["fixes"][:5]: print(f"   · [{f.get('dim')}] {str(f.get('fix'))[:110]}")
    print(f"\nGRADE: {verdict}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
