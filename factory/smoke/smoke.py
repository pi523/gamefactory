"""无头冒烟（harness）：按主题工序表通用驾驭。用法: smoke.py <theme> [out_dir] [recipe]"""
import http.server, socketserver, threading, socket, time, sys, urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[2]   # 仓库根
theme = sys.argv[1] if len(sys.argv) > 1 else "bar"
out = Path(sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "reports" / "smoke" / f"shots-{theme}")); out.mkdir(parents=True, exist_ok=True)
rq = ("&recipe=" + urllib.parse.quote(sys.argv[3])) if len(sys.argv) > 3 else ""
with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), lambda *a, **k: Q(*a, directory=str(ROOT), **k)); httpd.daemon_threads = True
threading.Thread(target=httpd.serve_forever, daemon=True).start()
errs, clips = [], []
def shot(pg, name, adv=0.0):
    if adv: pg.evaluate(f"() => window.__advance({adv})")
    pg.evaluate("() => window.__render()"); pg.screenshot(path=str(out / f"{name}.png"))
    c = pg.evaluate("() => window.__game.checkClipping()")
    if c: clips.append((name, c))
steps = [0]
def step(pg, tag, dt=0.1):
    """推进一步并做穿模检验（每一步都查，不只在截图帧）"""
    c = pg.evaluate(f"() => {{ window.__advance({dt}); return window.__game.checkClipping(); }}"); steps[0] += 1
    if c: clips.append((tag, c))
def run_auto(pg, phase, part):
    pg.evaluate(f"() => window.__game.auto.start('{phase}', '{part}')")
    for _ in range(600):
        if not pg.evaluate("() => window.__game.auto.busy()"): break
        step(pg, f"{phase}/{part}")
def heavy_pour(pg, phase):
    """重拖大流量（玩家把手指拖到底）时，倒的工具不许探进杯子"""
    pg.evaluate("() => { const g = window.__game; const k = (g.recipe.parts || []).map(([k]) => k).find((k) => k !== 'espresso'); if (k) g.selectIngredient(k); }")
    for _ in range(8): step(pg, f"{phase}/heavy-enter")
    pg.evaluate("() => window.__game.beginPour(400)")
    for _ in range(5): step(pg, f"{phase}/heavy-pour")
    pg.evaluate("() => window.__render()"); pg.screenshot(path=str(out / f"heavy-{phase}.png"))
    pg.evaluate("() => window.__game.endPour()")
    for _ in range(6): step(pg, f"{phase}/heavy-exit")
    if theme != "cafe": pg.evaluate("() => window.__game.onUndo()")   # 倒掉，评分不受重拖影响（咖啡馆倒掉会连浓缩一起倒掉，只倒半秒奶就算了）
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 390, "height": 844})
    pg.on("pageerror", lambda e: errs.append("PAGE: " + str(e))); pg.on("console", lambda m: errs.append("CONSOLE: " + m.text) if m.type == "error" else None)
    t0 = time.time(); pg.goto(f"http://127.0.0.1:{port}/drinks/game-drink/index.html?harness=1&theme={theme}{rq}")
    try: pg.wait_for_function("() => window.__game && window.__advance", timeout=20000); print("ready", round(time.time() - t0, 2), "s")
    except Exception: print("NOT READY"); print("\n".join(errs[:8])); b.close(); httpd.shutdown(); sys.exit(1)
    R = pg.evaluate("() => window.__game.recipe"); phases = pg.evaluate("() => window.__theme.phases"); print("recipe:", R["name"], "phases:", phases)
    for i, ph in enumerate(phases):
        if ph == "serve": break
        shot(pg, f"{i+1:02d}a-{ph}-start", 1.0)
        if ph == "pour": heavy_pour(pg, ph)
        run_auto(pg, ph, "mid"); shot(pg, f"{i+1:02d}b-{ph}-mid", 0.15)
        run_auto(pg, ph, "end"); shot(pg, f"{i+1:02d}c-{ph}-done", 1.0)
        pg.evaluate("() => window.__game.auto.next()"); pg.evaluate("() => window.__advance(0.4)")
    for j, w in enumerate([0.5, 1.2, 1.4, 1.2]): shot(pg, f"90-reveal-{j}", w)
    pg.evaluate("() => window.__advance(0.6)"); pg.wait_for_timeout(600); shot(pg, "99-score", 0.3)
    sc = pg.evaluate("() => window.__game.computeScore()")
    print("phase:", pg.evaluate("() => window.__game.phase"), "score:", sc["score"], sc["grade"], [f"{r[0]}={r[1]:.0f}" for r in sc["rows"]]); print("tips:", sc["tips"])
    b.close()
httpd.shutdown()
print("errors:", len(errs)); print("\n".join(errs[:8]))
uniq = {}
for n, c in clips:
    for m in c: uniq.setdefault(n.split("/")[0] + ": " + m.split("：")[0], [0, m])[0] += 1
print("CLIPPING:", sum(len(c) for _, c in clips), f"(checked {steps[0]} steps)"); [print("  ", k, "x%d" % v[0], v[1]) for k, v in list(uniq.items())[:8]]
