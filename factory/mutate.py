#!/usr/bin/env python3
"""扰动测试：往样例游戏里注入已知 bug，检验器必须变红；任一突变体 PASS 就说明闸门空转。
用法: python3 factory/mutate.py [games/sample-slice]
"""
import json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUT_DIR = ROOT / ".mutants"

MUTANTS = [
    ("score-never-increments", "game.js", "rt.setScore(rt.score + 1);", "rt.setScore(rt.score + 0);", "score 不涨"),
    ("throw-at-tick-100", "game.js", "  step(rt, dt) {", "  step(rt, dt) { if (rt.tick === 100) throw new Error('mutant');", "运行中抛异常"),
    ("no-viewport-meta", "index.html", '<meta name="viewport"', '<meta name="viewport-x"', "缺 viewport meta"),
    ("uses-eval", "game.js", "const size = slot.r * 1.8;", "const size = eval('slot.r * 1.8');", "使用 eval"),
    ("never-ends", "game.js", "rt.setLives(rt.lives - 1); rt.loseLifeFx(); if (rt.lives <= 0)", "rt.setLives(rt.lives - 0); rt.loseLifeFx(); if (rt.lives <= 0)", "命不减，永不结束"),
    ("external-url", "index.html", '"three":"../../vendor/three.module.js"', '"three":"https://example.com/three.js"', "引用外网资源"),
    ("no-boot", "game.js", "boot(game, {", "// boot(game, {", "不启动运行时（无契约）"),
    ("nondeterministic", "game.js", "stay: this.stay(rt) };", "stay: this.stay(rt) * (0.8 + Math.random() * 0.4) };", "同种子不可复现"),
    ("state-lies", "game.js", "return [{ id: a.id, kind: a.kind, x: b.x,", "return [{ id: a.id, kind: a.kind, x: b.x + 160,", "状态坐标与画面错位"),
    ("no-stage", "index.html", '<div id="stage">', '<div id="stage-x">', "没有竖屏 stage 容器"),
    ("floating", "game.js", "rt.placeInSlot(a.sprite, a.slot, k);", "rt.placeInSlot(a.sprite, { x: a.slot.x, y: a.slot.y - 180, r: a.slot.r }, k);", "物件悬在锚点上方 180px"),
]


# 第二靶子：多动词标杆样例（拖/点/滑）。用 `mutate.py games/sample-grill` 跑这组
MUTANTS_GRILL = [
    ("drop-ignored", "game.js", "if (anchor && dist <= anchor.r * 1.5 && !this.slotItem(anchor)) {", "if (false) {", "拖到烤位不生效（永远弹回托盘）"),
    ("swipe-ignored", "game.js", "else if (g.type === 'swipe' && g.dir === 'right' && s.state === '金黄') {", "else if (false) {", "右滑出餐不生效"),
    ("wrong-drag-target", "game.js", "action: 'drag', to: { x: free.x, y: free.y }, anchored: false, hint", "action: 'drag', to: { x: free.x, y: free.y - 150 }, anchored: false, hint", "声明的拖放目的地悬在锚点上方 150px"),
    ("never-burns", "game.js", "s.cook += dt * (s.flipped ? 1 : 0.85) * (this.served < 3 ? 0.5 : 1);", "s.cook += dt * (s.flipped ? 1 : 0.85) * (this.served < 3 ? 0.5 : 1) * (s.cook > 4 ? 0 : 1);", "永不烤焦（靠倒计时才结束，机器人仍能得分：应仍 PASS，用来证明不是所有改动都红）"),
    ("no-onboarding", "game.js", "tapToRestart: true });", "tapToRestart: true, tutorial: false });", "关闭新手引导（应红：hintsShown=0）"),
    ("no-emotion", "game.js", "tapToRestart: true });", "tapToRestart: true, praise: {}, milestones: {} });", "关闭情绪反馈（应红：praisesShown=0）"),
    ("cook-off-anchor", "game.js", "s.where = 'grill'; s.slot = anchor; s.cook = 0; rt.placeInSlot(s.sprite, anchor, 1);", "s.where = 'grill'; s.slot = anchor; s.cook = 0; rt.placeInSlot(s.sprite, { x: anchor.x, y: anchor.y - 170, r: anchor.r }, 1);", "串烤在锚点上方 170px（悬空）"),
]


# 第三靶子：厂房 01 教学课（vendor/bf-lesson.js 装配出的 games/<dish>）。用 `mutate.py games/tomato-egg` 跑这组；
# 教学课规则（每步可完成、每步 1 次反馈、素材键一致、无命数、慢手 ≥2 星）此前从没被扰动过——没有突变体的规则视为不存在。
MUTANTS_LESSON = [
    ("lesson-kind-bogus", "game.js", '"kind": "', '"kind": "bogus-', "第一步步型不存在（该步无法完成 → 步数/反馈/星级都该红）"),
    ("lesson-null-step", "game.js", '"steps": [', '"steps": [ null,', "步骤里混入 null（引擎运行时异常）"),
    ("lesson-ghost-ingredient", "game.js", '"ingredient": "', '"ingredient": "幽灵', "目标 kind 不在 BF_ASSETS 键里（备料画不出来）"),
    ("lesson-no-boot", "game.js", "bootLesson(LESSON,", "// bootLesson(LESSON,", "不启动引擎（无 __bf 契约）"),
    ("lesson-no-stage", "index.html", '<div id="stage">', '<div id="stage-x">', "没有竖屏 stage 容器"),
    ("lesson-external-url", "index.html", '"three":"../../vendor/three.module.js"', '"three":"https://example.com/three.js"', "引用外网资源"),
    ("lesson-praise-text", "game.js", 'bootLesson(LESSON, { praise: {"3": "', 'bootLesson(LESSON, { praise: {"3": "文案改了 ', "只改赞美文案（应仍 PASS：证明不是任何改动都红）"),
]


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "games/sample-runtime").resolve()
    global MUTANTS
    if src.name == "sample-grill": MUTANTS = MUTANTS_GRILL
    elif (src / "game.js").exists() and "bootLesson(" in (src / "game.js").read_text(encoding="utf-8"): MUTANTS = MUTANTS_LESSON
    if MUT_DIR.exists(): shutil.rmtree(MUT_DIR)
    results = []
    for spec in MUTANTS:
        name, file, old, new, desc = spec[:5]; expect = "PASS" if "应仍 PASS" in desc else "FAIL"
        dst = MUT_DIR / name
        shutil.copytree(src, dst)
        p = dst / file
        txt = p.read_text(encoding="utf-8")
        if old not in txt:
            results.append((name, desc, "SKIP(锚点不存在)")); continue
        p.write_text(txt.replace(old, new, 1), encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "factory/verify.py"), str(dst), "--out", str(MUT_DIR / "reports")],
                           capture_output=True, text=True)
        verdict = next((l.split(":", 1)[1].strip() for l in r.stdout.splitlines() if l.startswith("VERDICT:")), "ERROR")
        first_fail = next((l.strip() for l in r.stdout.splitlines() if l.strip().startswith("✗")), "")
        results.append((name, desc, verdict, first_fail, expect))

    bad = 0
    print(f"{'突变体':28} {'注入的 bug':16} 检验器裁决")
    for r in results:
        expect = r[4] if len(r) > 4 else "FAIL"
        ok = r[2] == expect
        bad += 0 if ok else 1
        tag = ("✓ 变红" if r[2] == "FAIL" else "✓ 保持绿（预期）") if ok else ("✗ 未变红 ← 闸门空转" if expect == "FAIL" else "✗ 误红 ← 检验器过严")
        print(f"{r[0]:28} {r[1][:18]:18} {tag}  {r[3] if len(r) > 3 else ''}")
    (MUT_DIR / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import ledger; ledger.record(src, "mutate", verdict=("ALL_CAUGHT" if bad == 0 else f"{bad}_ESCAPED"), mutants=[(r[0], r[2]) for r in results])
    except Exception: pass
    print(f"MUTATION: {'ALL_CAUGHT' if bad == 0 else f'{bad}_ESCAPED'}")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
