#!/usr/bin/env python3
"""终审包：生成 showcase/index.html —— 每款游戏一张卡：手机框内嵌试玩、最新检验裁决、视觉评审分与问题、截图、PRD 摘要、费用。
判官在出货口：只有 VERDICT: PASS、报告比产物新、（厂房课）REALISM: PASS 的游戏才进终审页；其余进「拦下」表，写明原因，不给试玩框。
用法: .venv/bin/python factory/showcase.py   → 打开 http://localhost:8000/showcase/
最后一行: SHOWCASE: <出厂数> shipped / <拦下数> blocked
"""
import glob, html, json, os, shutil, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "showcase"; OUT.mkdir(exist_ok=True); (OUT / "shots").mkdir(exist_ok=True)


def latest_report(gid):
    reps = sorted(glob.glob(str(ROOT / "reports" / f"{gid}-*" / "report.json")), key=os.path.getmtime)
    return json.loads(Path(reps[-1]).read_text(encoding="utf-8")) if reps else None


def cost(gid):
    tot = 0.0
    usage = ROOT / "reports/llm-usage.jsonl"
    if not usage.exists(): return 0.0
    for l in usage.read_text(encoding="utf-8").splitlines():
        r = json.loads(l)
        if f":{gid}" in r["tag"] or r["tag"].endswith(gid): tot += r.get("cost") or 0
    return tot


def gate(gdir: Path, prd, rep):
    """出货判据：返回 (能否出厂, 原因列表, 真实感裁决)。判的必须是现在这份产物：报告时间戳 ≥ index.html/game.js 的修改时间。"""
    reasons = []
    verdict = rep["verdict"] if rep else "未检验"
    if verdict != "PASS": reasons.append(f"机器检验 {verdict}")
    art_mtime = max([(gdir / f).stat().st_mtime for f in ("index.html", "game.js") if (gdir / f).exists()] or [0])
    if rep:
        try: rep_t = time.mktime(time.strptime(rep["ts"], "%Y%m%d-%H%M%S"))
        except Exception: rep_t = 0
        if rep_t + 1 < art_mtime: reasons.append(f"报告（{rep['ts']}）比产物旧：改完没复验")
    rr = json.loads((gdir / "realism-review.json").read_text(encoding="utf-8")) if (gdir / "realism-review.json").exists() else None
    realism = rr["verdict"] if rr else "未审"
    if prd.get("workshop"):   # 厂房课：硬要求 4，REALISM: PASS 才能进终审页（specs/workshop-cooking.md）
        if realism != "PASS": reasons.append(f"真实感审查 {realism}" + (f"：{'；'.join(str(f.get('why',''))[:40] for f in rr.get('fails', [])[:2])}" if rr and rr.get("fails") else ""))
        elif rr:
            try: rr_t = time.mktime(time.strptime(rr["ts"], "%Y-%m-%d %H:%M:%S"))
            except Exception: rr_t = 0
            if rr_t + 1 < art_mtime: reasons.append(f"真实感审查（{rr['ts']}）比产物旧：改完没复审")
    return (not reasons), reasons, realism


def card(gdir: Path):
    gid = gdir.name
    prd = json.loads((gdir / "prd.json").read_text(encoding="utf-8")) if (gdir / "prd.json").exists() else {"title": gid, "one_liner": "", "requirements": [], "moons": []}
    rep = latest_report(gid); vr = json.loads((gdir / "visual-review.json").read_text(encoding="utf-8")) if (gdir / "visual-review.json").exists() else None
    ship, reasons, realism = gate(gdir, prd, rep)
    shots = []
    if rep:
        rdir = ROOT / "reports" / f"{gid}-{rep['ts']}"
        for name in ("mobile-menu.png", "mobile-playing.png", "mobile-over.png", "desktop-playing.png"):
            src = rdir / name
            if src.exists():
                dst = OUT / "shots" / f"{gid}-{name}"; shutil.copy(src, dst); shots.append(f"shots/{dst.name}")
    verdict = rep["verdict"] if rep else "未检验"
    vp = rep["viewports"][0] if rep and rep["viewports"] else {}
    stats = []
    if vp:
        stats.append(f"启动 {vp.get('startup_ms')}ms")
        if vp.get("games"): stats.append("机器人局分 " + "/".join(str(g["final"]["score"]) for g in vp["games"]))
        if "layout_violation_ratio" in vp: stats.append(f"悬空率 {vp['layout_violation_ratio']:.0%}")
        if vp.get("render"): stats.append(f"渲染集中度 {(vp['render'].get('energy_ratio') or 0):.0%}")
    ev = {}
    for r in prd.get("requirements", []): ev[r.get("evidence", "?")] = ev.get(r.get("evidence", "?"), 0) + 1
    issues = "".join(f"<li><b>{html.escape(str(i.get('where', '')))}</b>：{html.escape(str(i.get('problem', '')))}</li>" for i in (vr or {}).get("issues", [])[:5])
    moons = "、".join(f"<a href='{html.escape(m.get('source') or '#')}' target='_blank'>{html.escape(m['name'])}</a>" for m in prd.get("moons", []))
    title = html.escape(prd.get("title", gid))
    if not ship:
        row = f"""<tr><td><b>{title}</b><br><span class="meta">{gid}</span></td><td><span class="v {verdict}">{verdict}</span> <span class="v {realism}">真实感 {realism}</span></td><td>{'<br>'.join(html.escape(r) for r in reasons)}</td><td>{''.join(f'<img src="{s}">' for s in shots[:2])}</td></tr>"""
        return None, row, reasons
    sec = f"""
<section class="card">
  <div class="phone"><iframe src="../games/{gid}/index.html" loading="lazy"></iframe></div>
  <div class="info">
    <h2>{title} <span class="v {verdict}">{verdict}</span> <span class="v {realism}">真实感 {realism}</span> <span class="score">视觉 {vr.get('score', '–') if vr else '–'}/5</span></h2>
    <p class="one">{html.escape(prd.get('one_liner', ''))}</p>
    <p class="meta">{html.escape(' · '.join(stats))} · 费用 ${cost(gid):.2f} · 证据 {html.escape(json.dumps(ev, ensure_ascii=False))}</p>
    <p class="meta">场景 {html.escape(str(prd.get('scene_type', '')))} · 布局 {html.escape(str((prd.get('layout') or {}).get('zh', '')))}</p>
    <p class="meta">月亮：{moons or '无'}</p>
    <div class="shots">{''.join(f'<img src="{s}">' for s in shots)}</div>
    <details><summary>视觉评审问题（前 5 条）</summary><ul>{issues or '<li>无</li>'}</ul></details>
    <details><summary>PRD 需求（{len(prd.get('requirements', []))} 条）</summary><ul>{''.join(f"<li>{html.escape(r['id'])} {html.escape(r['evidence'])} · {html.escape(r['text'])}</li>" for r in prd.get('requirements', []))}</ul></details>
    <p class="links"><a href="../games/{gid}/index.html" target="_blank">新窗口试玩</a> · <a href="../games/{gid}/prd.json" target="_blank">prd.json</a> · <a href="../games/{gid}/visual-review.json" target="_blank">visual-review.json</a>{' · <a href="../games/'+gid+'/realism-review.json" target="_blank">realism-review.json</a>' if (gdir/'realism-review.json').exists() else ''}{' · <a href="../games/'+gid+'/research.md" target="_blank">research.md</a>' if (gdir/'research.md').exists() else ''}</p>
  </div>
</section>"""
    return sec, None, []


def main():
    games = [d for d in sorted((ROOT / "games").iterdir()) if (d / "index.html").exists() and not d.name.startswith("sample") and not d.name.startswith("_")]
    shipped, blocked = [], []
    for g in games:
        sec, row, reasons = card(g)
        if sec: shipped.append(sec)
        else: blocked.append((g.name, row, reasons))
    blocked_html = ""
    if blocked:
        blocked_html = f"""<section class="blocked"><h2>拦下（不进终审）· {len(blocked)} 款</h2>
<p class="meta">判官没放行的不给试玩框。原因逐条列出；改完要重跑 verify / realism_review 再生成本页。</p>
<table><tr><th>游戏</th><th>裁决</th><th>拦下原因</th><th>最近截图</th></tr>{''.join(r for _, r, _ in blocked)}</table></section>"""
    page = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>黑灯工厂 · 终审</title>
<style>
body{{margin:0;background:#0d0b0a;color:#f3ede4;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}}
header{{padding:20px 28px;border-bottom:1px solid rgba(201,168,106,.35)}} h1{{margin:0;color:#c9a86a;font-size:22px}} header p{{color:#b8ae9f;margin:6px 0 0}}
.card{{display:flex;gap:24px;padding:24px 28px;border-bottom:1px solid rgba(255,255,255,.06)}}
.phone{{flex:0 0 300px;height:640px;border:6px solid #2a2320;border-radius:28px;overflow:hidden;background:#000;box-shadow:0 10px 40px rgba(0,0,0,.6)}}
.phone iframe{{width:100%;height:100%;border:0}}
.info{{flex:1;min-width:0}} h2{{margin:0 0 6px;font-size:20px;color:#f3ede4}}
.v{{font-size:12px;padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle}} .PASS{{background:#2f5d3a;color:#c9f0cf}} .FAIL{{background:#6b2a26;color:#f7c9c4}} .未检验,.未审{{background:#444}}
.score{{font-size:13px;color:#c9a86a;margin-left:8px}} .one{{color:#f3ede4;margin:4px 0 8px}} .meta{{color:#b8ae9f;font-size:13px;margin:3px 0}} .meta a{{color:#c9a86a}}
.shots{{display:flex;gap:8px;margin:10px 0;overflow-x:auto}} .shots img{{height:220px;border-radius:8px;border:1px solid rgba(255,255,255,.08)}}
details{{margin:8px 0;color:#b8ae9f;font-size:13px}} summary{{cursor:pointer;color:#c9a86a}} ul{{margin:6px 0;padding-left:18px}} li{{margin:3px 0}}
.links a{{color:#c9a86a;font-size:13px}}
.blocked{{padding:24px 28px;border-top:2px solid #6b2a26}} .blocked h2{{color:#f7c9c4}} .blocked table{{width:100%;border-collapse:collapse;font-size:13px}} .blocked td,.blocked th{{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid rgba(255,255,255,.08)}} .blocked img{{height:120px;border-radius:6px;margin-right:6px}}
</style></head><body>
<header><h1>黑灯工厂 · 人工终审</h1><p>左边手机框可直接玩（也可用手机访问同一地址）。进到这页的每一款都已由机器放行：能跑、不报错、可玩通、可复现、竖屏、落在锚点上、（厂房课）整课真实感审查通过、报告比产物新。你只判：好不好玩、像不像游戏。出厂 {len(shipped)} 款 · 拦下 {len(blocked)} 款。</p></header>
{''.join(shipped) or '<p class="meta" style="padding:28px">目前没有一款被判官放行。</p>'}
{blocked_html}
</body></html>"""
    (OUT / "index.html").write_text(page, encoding="utf-8")
    for gid, _, reasons in blocked: print(f"  拦下 {gid}: {'；'.join(reasons)}")
    print(f"终审页 → showcase/index.html（出厂 {len(shipped)} 款 · 拦下 {len(blocked)} 款）")
    print(f"SHOWCASE: {len(shipped)} shipped / {len(blocked)} blocked")


if __name__ == "__main__":
    main()
