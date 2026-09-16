#!/usr/bin/env python3
"""复刻保真环：机器人玩我们的游戏并按 1fps 录帧 → 与参考视频同一套抽帧/拼图/视觉提问 → 两份结构化观察逐项比对 → 差异清单。
用法:
  .venv/bin/python factory/fidelity.py games/bbq-skewer                  # 参考 = research.json 里 videos[-1]（或 --ref-index N / --ref-title 关键词）
  .venv/bin/python factory/fidelity.py games/bbq-skewer --ref-title "Grill Rush"
产出: games/<id>/fidelity.json（score 0-100、diffs[]、ours、ref）、fidelity.md、play/ 下的拼图。
generate.py --fidelity 会把 diffs 当驳回意见回灌（保真分 < --fidelity-pass 时）。
"""
import argparse, http.server, io, json, socket, socketserver, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm, bot  # noqa: E402
from video_research import SHEET_Q, make_sheets, observe_style, palette_kmeans  # noqa: E402

COMPARE_Q = """你是游戏复刻的验收员。下面是【参考游戏】和【复刻游戏】各一份基于实机帧的结构化观察（同一套提问得到）。
请逐项比对并只输出 JSON：
{"score": 0-100 的保真分,
 "diffs": [{"aspect": "layout|verbs|cadence|states|hud|feedback|fail_state|difficulty|camera|style",
            "ref": "参考里是什么", "ours": "复刻里是什么", "severity": "high|mid|low",
            "route": "prd_layout|assets|code",
            "fix": "具体改法，能直接执行"}],
 "layout_fix": {"type": "slots|path", "count": 数字, "zh": "背景里要画出的容器/轨道中文描述", "en": "同上英文，含数量/排列/透视"} 或 null,
 "same": ["已经一致的方面"]}
route 规则：容器数量/排列/透视不一致 → prd_layout（并填 layout_fix，count 取参考里可数出的数量）；贴图/状态图缺失 → assets；动词/节奏/状态机/HUD/反馈/失败态 → code。
范围规则：复刻只覆盖【复刻 PRD 范围】里描述的环节。若参考游戏是多工位/多关卡的大游戏，只比对与该范围对应的环节（例如只比"烤盘"工位），参考里其它环节（备料、装盘、经济系统）不算差异、也不扣分。
评分规则：核心循环与动词不一致 -30；布局（容器数量/排列）不一致 -20；节奏（出现间隔、窗口）差 >50% -15；状态序列不一致 -10；HUD 项目与位置 -10；反馈缺失 -10；失败态不一致 -5。
风格（style）也要比：美术类型、色调、UI 质感与参考是否同一路数（模仿风格不复制素材）；风格不像 -10。参考里“未见”的项不比。

【复刻 PRD 范围】
{scope}

【参考游戏】
{ref}

【复刻游戏】
{ours}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def record_play(game_dir: Path, seconds=45, fps=1, W=390, H=844):
    """机器人边玩边按 fps 截图（真实 CSS 像素），返回 [(t, PIL.Image)]"""
    from playwright.sync_api import sync_playwright
    from PIL import Image
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), lambda *a, **k: Quiet(*a, directory=str(ROOT), **k)); httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    frames = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(f"http://127.0.0.1:{port}/{game_dir.relative_to(ROOT).as_posix()}/index.html")
            pg.wait_for_function("() => window.__bf && window.__bf.ready", timeout=15000)
            pg.evaluate("() => { window.__bf.setTimeScale(1); window.__bf.reset(11); }")
            frames.append((0.0, Image.open(io.BytesIO(pg.screenshot())).convert("RGB")))
            pg.mouse.click(W / 2, H / 2); t0 = time.time(); last_shot = -1
            while time.time() - t0 < seconds:
                st = pg.evaluate("() => window.__bf.state()")
                if st["phase"] == "over": frames.append((time.time() - t0, Image.open(io.BytesIO(pg.screenshot())).convert("RGB"))); break
                el = time.time() - t0
                if int(el * fps) > last_shot:
                    last_shot = int(el * fps); frames.append((el, Image.open(io.BytesIO(pg.screenshot())).convert("RGB")))
                cands = [t for t in st["targets"] if 0.05 * H < t["y"] < 0.95 * H]
                if cands: bot.do_action(pg, cands[0]); pg.wait_for_timeout(120)
                else: pg.wait_for_timeout(80)
            b.close()
    finally:
        httpd.shutdown()
    return frames


def observe(sheets, name, gid):
    import numpy as np  # noqa: F401  (opencv 依赖)
    parts = []
    for i in range(0, len(sheets), 2):
        chunk = sheets[i:i + 2]
        parts.append(llm.chat_json([{"role": "user", "content": [{"type": "text", "text": SHEET_Q.format(name=name)}] + [llm.image_part(str(s)) for s in chunk]}],
                                   role="vision", max_tokens=6000, tag=f"fidelity:{gid}:ours"))
    if len(parts) == 1: return parts[0]
    from video_research import MERGE_Q
    return llm.chat_json([{"role": "user", "content": MERGE_Q.format(parts=json.dumps(parts, ensure_ascii=False))}], role="cheap", max_tokens=6000, tag=f"fidelity:{gid}:merge")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_dir"); ap.add_argument("--ref-index", type=int, default=None); ap.add_argument("--ref-title", default=None)
    ap.add_argument("--seconds", type=int, default=45)
    ap.add_argument("--ref-research", default=None, help="参考视频观察从哪份 research.json 取（厂房课共用 games/_workshop-cooking/research.json；不给则用本游戏目录的）")
    ap.add_argument("--min-score", type=int, default=None, help="保真分低于此值退出码 1（作门槛用；不给只记录）")
    a = ap.parse_args()
    game = Path(a.game_dir).resolve(); gid = game.name
    research = json.loads((Path(a.ref_research).resolve() if a.ref_research else (game / "research.json")).read_text(encoding="utf-8"))
    vids = research.get("videos", [])
    if not vids: raise SystemExit("research.json 里没有 videos，先跑 video_research.py")
    usable = [v for v in vids if v.get("relevant", True)] or vids
    ref = vids[a.ref_index] if a.ref_index is not None else (next((v for v in usable if a.ref_title and a.ref_title.lower() in (v.get("title") or "").lower()), None) or usable[-1])
    print(f"参考：{ref.get('title')} ({ref.get('video')})")

    import cv2, numpy as np
    t0 = time.time(); frames = record_play(game, a.seconds)
    cv_frames = [(t, cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)) for t, im in frames]
    sheets = make_sheets(cv_frames, game / "play", per=12, max_sheets=4)
    print(f"机器人游玩录帧 {len(frames)} 张 → 拼图 {len(sheets)} ({time.time()-t0:.0f}s)")
    ours = observe(sheets, json.loads((game / "prd.json").read_text(encoding="utf-8")).get("title", gid), gid)
    ours["style"] = observe_style(gid, sheets, gid) or {}
    if ours["style"]: ours["style"]["palette_kmeans"] = palette_kmeans(cv_frames)
    keys = ("core_loop", "cadence", "hud", "feedback", "fail_state", "difficulty", "camera", "numbers", "style")
    prd = json.loads((game / "prd.json").read_text(encoding="utf-8"))
    scope = json.dumps({"core_loop": prd.get("core_loop"), "layout": prd.get("layout"), "controls": prd.get("controls")}, ensure_ascii=False)
    cmp = llm.chat_json([{"role": "user", "content": COMPARE_Q.replace("{scope}", scope).replace("{ref}", json.dumps({k: ref.get(k) for k in keys}, ensure_ascii=False)).replace("{ours}", json.dumps({k: ours.get(k) for k in keys}, ensure_ascii=False))}],
                        role="code", max_tokens=6000, tag=f"fidelity:{gid}:compare")
    out = {"ref_title": ref.get("title"), "ref_video": ref.get("video"), "score": cmp.get("score"), "diffs": cmp.get("diffs", []), "same": cmp.get("same", []), "layout_fix": cmp.get("layout_fix"),
           "ours": ours, "ref": {k: ref.get(k) for k in keys}, "sheets": [str(s.relative_to(ROOT)) for s in sheets], "ts": time.strftime("%F %T")}
    (game / "fidelity.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (game / "fidelity-log.jsonl").open("a", encoding="utf-8").write(json.dumps({"ts": out["ts"], "score": out["score"], "n_diffs": len(out["diffs"]), "ref": out["ref_title"]}, ensure_ascii=False) + "\n")
    md = [f"# 保真比对：{gid} vs {ref.get('title')}\n", f"_{out['ts']} · 保真分 {out['score']}/100_\n", "## 差异\n"]
    md += [f"- **[{d.get('severity')}] {d.get('aspect')}**：参考「{d.get('ref')}」 / 复刻「{d.get('ours')}」 → 改法：{d.get('fix')}" for d in out["diffs"]]
    md += ["\n## 一致\n"] + [f"- {s}" for s in out["same"]] + ["\n## 复刻观察（机器人游玩帧）\n```json\n" + json.dumps(ours, ensure_ascii=False, indent=1) + "\n```"]
    (game / "fidelity.md").write_text("\n".join(md), encoding="utf-8")
    print(f"保真分 {out['score']}/100 · 差异 {len(out['diffs'])} 条（high {sum(1 for d in out['diffs'] if d.get('severity')=='high')}）→ games/{gid}/fidelity.md")
    for d in out["diffs"][:6]: print(f"  · [{d.get('severity')}] {d.get('aspect')}: {str(d.get('ours'))[:60]} ≠ {str(d.get('ref'))[:60]}")
    print(f"FIDELITY: {out['score']}")
    try:
        import ledger; ledger.record(game, "fidelity", verdict=("PASS" if a.min_score is None or (out["score"] or 0) >= a.min_score else "FAIL"), score=out["score"], ref=out["ref_title"], n_diffs=len(out["diffs"]))
    except Exception: pass
    if a.min_score is not None and (out["score"] or 0) < a.min_score: sys.exit(1)


if __name__ == "__main__":
    main()
