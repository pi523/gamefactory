"""手作模拟品类检验器：无头浏览器按模块自己的工序表驾驭一整局（auto mid/end），每推进 0.1s 查一次
window.__game.checkClipping()（含组装/倒液物理），结算必须出分；截图落 reports/craft/<id>/。
用法: craft_verify.py games/<id> [--json out.json]   →  stdout 末行 CRAFT: PASS|FAIL
"""
import argparse, http.server, json, socket, socketserver, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def run(game_dir: Path, out: Path, text_limit=14):
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), lambda *a, **k: Q(*a, directory=str(ROOT), **k)); httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    rel = game_dir.resolve().relative_to(ROOT).as_posix()
    R = {"errors": [], "clips": [], "steps": 0, "phases": [], "score": None, "grade": None, "text_too_long": [], "hints": []}
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 540, "height": 960})
        pg.on("pageerror", lambda e: R["errors"].append(str(e)[:300]))
        pg.on("console", lambda m: R["errors"].append("console: " + m.text[:300]) if m.type == "error" else None)
        pg.goto(f"http://127.0.0.1:{port}/{rel}/index.html?harness=1"); pg.wait_for_timeout(2500)
        if R["errors"]:   # 语法错就给行列（浏览器只报一句 Invalid token），用 acorn 定位
            try:
                pg2 = b.new_page(); pg2.set_content('<script src="https://cdnjs.cloudflare.com/ajax/libs/acorn/8.11.3/acorn.min.js"></script>'); pg2.wait_for_function("() => window.acorn", timeout=15000)
                src = (game_dir / "game.js").read_text(encoding="utf-8")
                loc = pg2.evaluate("(src) => { try { acorn.parse(src, {ecmaVersion: 2022, sourceType: 'module'}); return null; } catch (e) { return e.message; } }", src)
                if loc:
                    import re as _re; m = _re.search(r"\((\d+):(\d+)\)", loc); ln = int(m.group(1)) if m else 0
                    lines = src.split("\n"); ctx = lines[ln - 1][:200] if 0 < ln <= len(lines) else ""
                    R["errors"].append(f"语法错误 {loc}；那一行：{ctx}")
            except Exception as e: R["errors"].append("acorn 定位失败：" + str(e)[:80])
            b.close(); httpd.shutdown(); return R
        try: phases = pg.evaluate("() => window.__theme.phases")
        except Exception as e: R["errors"].append("没有 window.__theme.phases：" + str(e)[:120]); b.close(); httpd.shutdown(); return R
        R["phases"] = phases
        if len(phases) < 3 or phases[-1] != "serve": R["errors"].append(f"工序表要 3–5 道且最后是 serve，现在是 {phases}")
        def step(tag, dt=0.1):
            c = pg.evaluate(f"() => {{ window.__advance({dt}); return window.__game.checkClipping(); }}"); R["steps"] += 1
            if c: R["clips"].append((tag, c))
            h = pg.evaluate("() => document.getElementById('hint').textContent"); R["hints"].append(h)
        def shot(name, adv=0.0):
            if adv: pg.evaluate(f"() => window.__advance({adv})")
            pg.evaluate("() => window.__render()"); pg.screenshot(path=str(out / f"{name}.png"))
            c = pg.evaluate("() => window.__game.checkClipping()")
            if c: R["clips"].append((name, c))
        def run_auto(ph, part):
            pg.evaluate(f"() => window.__game.auto.start('{ph}', '{part}')")
            for _ in range(600):
                if not pg.evaluate("() => window.__game.auto.busy()"): return True
                step(f"{ph}/{part}")
            R["errors"].append(f"auto({ph},{part}) 600 步没结束"); return False
        for i, ph in enumerate(phases):
            if ph == "serve": break
            shot(f"{i+1:02d}a-{ph}-start", 0.3)
            run_auto(ph, "mid"); shot(f"{i+1:02d}b-{ph}-mid", 0.15)
            run_auto(ph, "end"); shot(f"{i+1:02d}c-{ph}-done", 0.6)
            ok = pg.evaluate(f"() => window.__game.G.canNext ? window.__game.G.canNext(window.__game, '{ph}') !== false : true")
            if not ok: R["errors"].append(f"工序 {ph} auto end 之后 canNext 仍为 false")
            pg.evaluate("() => window.__game.auto.next()"); step("next", 0.4)
        for k in range(4): shot(f"90-reveal-{k}", 1.2)
        for _ in range(40):
            if pg.evaluate("() => window.__game.phase") == "score": break
            step("toscore", 0.3)
        shot("99-score", 0.5)
        try:
            R["score"] = pg.evaluate("() => parseInt(document.getElementById('score-total').textContent)")
            R["grade"] = pg.evaluate("() => document.getElementById('grade').textContent")
        except Exception as e: R["errors"].append("结算没出分：" + str(e)[:120])
        if pg.evaluate("() => window.__game.phase") != "score": R["errors"].append("没走到结算")
        b.close()
    httpd.shutdown()
    for h in sorted(set(R["hints"])):
        if len(h) > text_limit + 4: R["text_too_long"].append(h)
    return R


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("game"); ap.add_argument("--json", default=None); a = ap.parse_args()
    game = Path(a.game); gid = game.name; out = ROOT / "reports" / "craft" / gid
    t0 = time.time(); R = run(game, out); R["seconds"] = round(time.time() - t0, 1)
    uniq = {}
    for tag, c in R["clips"]:
        for m in c: uniq.setdefault(m, [0, tag]); uniq[m][0] += 1
    R["clip_summary"] = [f"{m} ×{n}（首见 {tag}）" for m, (n, tag) in uniq.items()]
    passed = not R["errors"] and not R["clips"] and R["score"] is not None
    R["pass"] = passed
    if a.json: Path(a.json).write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"phases: {R['phases']}  steps: {R['steps']}  score: {R['score']} {R['grade']}  {R['seconds']}s")
    for e in R["errors"][:8]: print("  ✗", e)
    for c in R["clip_summary"][:8]: print("  ✗ 穿模/组装/物理:", c)
    for h in R["text_too_long"][:4]: print("  ⚠ 提示太长:", h)
    print("CRAFT: PASS" if passed else "CRAFT: FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
