#!/usr/bin/env python3
"""黑灯工厂一条命令：一句话题材 → 三路学习（网页竞品 / 竞品视频 / 做菜工艺）→ PRD → 背景即布局+专属素材 → 代码 → 五层检验 → 视觉评审 → 保真比对回灌 → 终审页。
用法:
  .venv/bin/python factory/pipeline.py "章鱼小丸子摊：往格子里倒面糊，半熟用签子翻面，烤到金黄夹走，烤焦掉命" --id takoyaki \\
      --dish "章鱼小丸子" --video-query "takoyaki game gameplay" --ref "takoyaki"
每一步的裁决写 games/<id>/pipeline-log.jsonl；任一步失败停下并打印该步日志路径。--skip 可跳过已完成的步（如 --skip research,video）。
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def step(name, cmd, game, must=True, tail=12):
    t0 = time.time(); print(f"\n━━ {name} ━━\n$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    out = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "Warning" not in l and not l.startswith("  __") and "注入完成" not in l)
    print("\n".join(out.splitlines()[-tail:]))
    ok = r.returncode == 0
    (game / "pipeline-log.jsonl").open("a", encoding="utf-8").write(json.dumps({"step": name, "ok": ok, "secs": round(time.time() - t0), "tail": out.splitlines()[-3:], "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
    if not ok and must:
        print(f"\n✗ {name} 失败，停。日志：games/{game.name}/pipeline-log.jsonl"); sys.exit(1)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("one_liner"); ap.add_argument("--id", required=True)
    ap.add_argument("--dish", default=None, help="做菜工艺学习的菜名（同事的 recipe-extractor）；不给则跳过工艺学习")
    ap.add_argument("--video-query", action="append", default=[], help="竞品实机视频搜索词，可多个；不给则按网页调研的竞品名搜")
    ap.add_argument("--ref", default=None, help="保真比对用哪段参考视频（标题关键词）；不给用最后一段")
    ap.add_argument("--skip", default="", help="跳过步骤，逗号分隔：research,video,moon,craft,prd,assets,generate,showcase")
    ap.add_argument("--attempts", type=int, default=3); ap.add_argument("--fidelity-attempts", type=int, default=2); ap.add_argument("--fidelity-pass", type=int, default=80)
    ap.add_argument("--workshop", choices=["cooking-lesson"], default=None, help="厂房模式：cooking-lesson = 菜名 → 工艺包 → 自动挑 2–3 步 → 教学课 PRD → 素材 → 生成")
    ap.add_argument("--lesson-fidelity-pass", type=int, default=70, help="厂房课对风格月亮（Cooking Simulator）的保真分门槛；70 是 2026-09-11 按番茄炒蛋首测 72 定的临时值，待三道菜都有分再定")
    a = ap.parse_args()
    if a.workshop == "cooking-lesson":
        dish = a.dish or a.one_liner
        game = ROOT / "games" / a.id; game.mkdir(parents=True, exist_ok=True); F = ROOT / "factory"
        (game / "pipeline-log.jsonl").open("a", encoding="utf-8").write(json.dumps({"step": "start", "workshop": "cooking-lesson", "dish": dish, "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
        skip = set(s.strip() for s in a.skip.split(",") if s.strip())
        if "craft" not in skip: step("① 工艺学习（做菜教学视频）", [PY, F / "craft_learn.py", dish, "--id", a.id, "--style", "家常"], game)
        if "steps" not in skip: step("② 自动挑关键步骤（有失败面优先，≤3 步 ≤2 动词）", [PY, F / "pick_steps.py", str(game)], game)
        if "prd" not in skip: step("③ 教学课 PRD（固定模板）", [PY, F / "make_lesson_prd.py", str(game)], game)
        if "assets" not in skip: step("④ 单口锅背景 + 状态贴图", [PY, F / "make_assets.py", str(game)], game)
        if "generate" not in skip: step("⑤ 手写教学课引擎装配 → 检验（教学课规则 + 慢手机器人）→ 真实感审查（硬要求 4）", [PY, F / "make_lesson_game.py", str(game)], game, tail=25)
        ref_research = ROOT / "games/_workshop-cooking/research.json"
        if "fidelity" not in skip and ref_research.exists():   # 对着月亮的判据：与厂房风格月亮（Cooking Simulator 实机）逐项比对，出差异表；分数低于 --fidelity-pass 即停
            step(f"⑤b 保真比对（对着月亮，门槛 {a.lesson_fidelity_pass}）", [PY, F / "fidelity.py", str(game), "--ref-research", str(ref_research), "--ref-title", "Cooking Simulator", "--min-score", str(a.lesson_fidelity_pass)], game, tail=8)
        if "showcase" not in skip: step("⑥ 终审页（判官在出货口：没放行的进拦下表）", [PY, F / "showcase.py"], game, must=False, tail=4)
        print(f"\nPIPELINE: DONE（厂房 01）→ http://localhost:8000/games/{a.id}/index.html"); return
    skip = set(s.strip() for s in a.skip.split(",") if s.strip())
    game = ROOT / "games" / a.id; game.mkdir(parents=True, exist_ok=True)
    (game / "pipeline-log.jsonl").open("a", encoding="utf-8").write(json.dumps({"step": "start", "one_liner": a.one_liner, "dish": a.dish, "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
    F = ROOT / "factory"

    if "research" not in skip:
        step("① 找月亮·网页", [PY, F / "research.py", a.one_liner, "--id", a.id], game)
    if "video" not in skip:
        cmd = [PY, F / "video_research.py", "--id", a.id, "--max", "2"]
        for q in a.video_query: cmd += ["--query", q]
        step("② 找月亮·竞品视频抽帧", cmd, game, must=False)
    if "moon" not in skip and (game / "research.json").exists():
        step("②b 选月亮（链接核实 + trinity 裁决）", [PY, F / "verify_links.py", str(game)], game, must=False, tail=8)
        step("②c 选月亮·trinity", [PY, F / "pick_moon.py", str(game)], game, must=False, tail=6)
    if a.dish and "craft" not in skip:
        step("③ 工艺学习·做菜视频（同事 recipe-extractor）", [PY, F / "craft_learn.py", a.dish, "--id", a.id], game, must=False)
    if "prd" not in skip:
        step("④ PRD（引用三路证据）", [PY, F / "make_prd.py", a.one_liner, "--id", a.id], game)
    if "assets" not in skip:
        step("⑤ 背景即布局 + 专属素材", [PY, F / "make_assets.py", str(game)], game)
    if "generate" not in skip:
        cmd = [PY, F / "generate.py", str(game), "--attempts", a.attempts, "--visual-attempts", "1"]
        if (game / "research.json").exists():
            cmd += ["--fidelity", "--fidelity-attempts", a.fidelity_attempts, "--fidelity-pass", a.fidelity_pass] + (["--ref-title", a.ref] if a.ref else [])
        step("⑥ 生成 → 检验 → 评审 → 保真回灌", cmd, game, tail=25)
    if "showcase" not in skip:
        step("⑦ 终审页", [PY, F / "showcase.py"], game, must=False, tail=2)
    fl = game / "fidelity-log.jsonl"
    if fl.exists():
        last = json.loads(fl.read_text(encoding="utf-8").splitlines()[-1]); print(f"\n保真分 {last['score']}/100（参考 {last['ref'][:40]}）")
    print(f"\nPIPELINE: DONE → http://localhost:8000/games/{a.id}/index.html · showcase/")


if __name__ == "__main__":
    main()
