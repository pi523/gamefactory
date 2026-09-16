#!/usr/bin/env python3
"""代码生成环：PRD + 调试契约 + 硬性规定 → LLM 产 index.html/game.js → verify.py 裁决 → 驳回报告回灌 → 重试，直到 PASS 或达上限。
用法: .venv/bin/python factory/generate.py games/<id> [--attempts 4] [--model anthropic/claude-opus-5] [--keep-going]
产物: games/<id>/index.html, game.js；每次尝试存 games/<id>/attempts/N/；台账 games/<id>/gen-log.jsonl。
最后一行固定打印 GENERATE: PASS|FAIL。PASS 后会自动注入真实素材并再验一次。
"""
import argparse, json, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402

FILE_RE = re.compile(r"=== FILE: (\S+) ===\n(.*?)(?=\n=== FILE: |\n=== END ===)", re.S)

SKELETON = r"""
// ---- 运行时 API（vendor/bf-runtime.js，已写死并验过；你只写玩法对象）----
import { boot } from '../../vendor/bf-runtime.js';
const game = {
  init(rt) {},                      // 一次性初始化（可选）。rt.anchors()/rt.path() 此时可用
  onResize(rt) {},                  // stage 尺寸变化时重算位置（可选）
  reset(rt, rng) {},                // 清场、重置自己的状态。rng 是确定性随机 ()=>[0,1)，所有随机只用它；rt 已把 score=0、lives=maxLives、phase='menu'
  onStart(rt) {},                   // menu→playing（可选）
  step(rt, dt) {},                  // 固定步长 1/60 s，只在 playing 时被调用；玩法全部在这里推进
  onTap(rt, x, y) {},               // 轻点（位移<12px）。x/y 为 stage 像素（左上原点、y 向下）；menu/over 的点击运行时已处理
  onDown(rt, x, y) {},              // 手指按下：通常在这里用 rt.hit(sp,x,y) 找被按住的物件，开始拖
  onMove(rt, x, y, dx, dy) {},      // 拖动中：sp.setCenter(x,y) 跟手
  onUp(rt, x, y, gesture) {},       // 松手：gesture={type:'tap'|'drag'|'swipe', dir:'left'|'right'|'up'|'down'|null, x0,y0,dx,dy,ms}
                                    //   drag 松手 → 用 rt.nearestAnchor(slots,x,y) 找目标锚点，dist<=r*1.5 才算放进去，否则回原位
  targets(rt) { return []; },       // 返回 [{id, kind, x, y, w, h, action, to?, dir?, anchored?}]，stage 像素、中心点。
                                    //   action:'tap'|'drag'（必带 to:{x,y} 目的地）|'swipe'（必带 dir）；不在锚点上的（托盘里/手里）标 anchored:false
                                    //   按紧急程度排序：机器人执行数组第一个可做的动作
                                    //   每个目标带 hint：'面糊定形了，滑一下翻面' 这类状态化人话（运行时首次教该动词时显示，比通用文案清楚得多）
};
boot(game, { title: '游戏名', overTitle: '结束标题', tapToRestart: true,   // 首页只有游戏名+开始按钮，不写玩法说明（运行时自动引导负责教）
  hints: { tap: '点它翻面', drag: '拖到烤位', swipe: '右滑出餐' },          // 新手引导文案（运行时自动在动词第一次出现时演示手势）
  praise: { 3: '漂亮！', 5: '火候到位！', 8: '烤神附体！', 12: '整条街最香！' }, // 连击赞美（4 秒内连续得分），题材化文案
  milestones: { 1: '开张！', 5: '上手了！', 10: '越来越熟练！', 20: '摊主本色！' },   // 分数里程碑赞美（慢节奏玩法靠这个）
  par: 10 });                                                                   // 2 星线，2×par 为 3 星
// 关键时刻可主动 rt.praise('刚刚好！')，如首次完美出餐。

// rt 提供（全部 stage 像素，k = stageH/844 是尺寸缩放系数）：
//   rt.SW, rt.SH, rt.k, rt.rng, rt.score, rt.lives, rt.t（本局秒）, rt.phase
//   rt.anchors({cols,rows})  → [{x,y,r}]  布局 slots（背景里真实画出的锅/格子），没有布局时给回退网格
//   rt.path() → {points:[{x,y}], width}；rt.pathAt(u∈0..1) → {x,y}  轨道型布局
//   rt.sprite(kind, sizePx, {rng, color, state}) → sp   贴图面片+脚下阴影；kind 必须是 BF_ASSETS 的键；sp.setState('金黄') 切多状态贴图（生/半熟/金黄/焦，缺图用色调兜底）
//   rt.hit(sp, x, y) → bool 点在物件上；rt.nearestAnchor(anchors, x, y) → {anchor, dist}
//       sp.setFoot(x, groundY)  底边贴地（轨道/台面上用）；rt.placeInSlot(sp, slot, k) 放进锅/格子（slots 布局一律用这个，k=冒头缩放 0→1）；sp.setCenter(x,y)；sp.setScale(k)；sp.setRotation(a)；sp.setVisible(v)；sp.remove()；sp.box() → {x,y,w,h}
//   rt.setScore(n)  rt.setLives(n, max?)  rt.setTimer(sec|null)  rt.gameOver(title, lines[])
//   rt.hitFlash(x,y)  rt.comboText(x,y,n)  rt.loseLifeFx()
// 物理规则：slots 布局用 rt.placeInSlot(sp, slot, k)（直径≈slot.r*1.8）；path 布局用 sp.setFoot(pathAt(u).x, pathAt(u).y)；冒出用 k 从 0→1；不许凭空出现在半空。
// 动词预算（检验器的慢手机器人会查：反应 0.7s、每秒 1 次操作，必须活过 40s 且得 5 分）：整局 ≤3 个动词；前 5 个物件只用 1 个动词，第 6 个起解锁第 2 个，第 12 个起解锁第 3 个；每个状态只有一种操作。解锁前该状态自动完成（如自动翻面），不要求玩家做。
// 热身与节奏硬规则（检验器会查）：开局前 6 秒不得掉命；完全不操作时第 2 次掉命不得早于 15 秒（前 15 秒最多丢 1 命）；前 3 个物件的等待/反应窗口 ≥ 正常 2 倍；开局前 30 秒同时需要玩家处理的物件 ≤ 2 个，托盘/供料区的物件不因超时扣命（至多回收）。按已完成数量与仿真时间判定，不用真实时钟。
// 托盘/供料区放在 stage 底部 y≈0.88*SH（sp.setFoot），这里的物件 targets 标 anchored:false；手里拖着的物件也标 anchored:false。
// 参考实现：games/sample-grill/game.js（拖串上烤位 → 半熟点翻面 → 金黄右滑出餐 → 焦掉命 → 60 秒倒计时），可直接借鉴其结构。
// 硬禁止（静态扫描直接 FAIL）：game.js 里出现 document.、innerHTML、.style、window.__bf、rt.scene/rt.renderer/rt.camera/rt.stage/rt.hud/rt.overlay、import 'three'、Math.random、Date.now、fetch、外网 URL。
// 画面全部交给运行时；你不能也不需要改背景铺法、加遮罩、写 CSS、加灯光。想要反馈只用 rt.hitFlash/comboText/loseLifeFx。
"""

INDEX_TEMPLATE = """index.html 固定为（除 <title> 外不要改）：
<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">
<title>游戏名</title>
<script type="importmap">{"imports":{"three":"../../vendor/three.module.js"}}</script></head>
<body><div id="stage"><div id="bg"></div><canvas id="c"></canvas><div id="hud"></div><div id="overlay"></div></div>
<script>window.BF_ASSETS = {};</script>
<script type="module" src="./game.js"></script></body></html>"""


def build_system(prd, contract, rules, manifest_names, style, local_assets, game=None):
    ui = json.dumps(style["ui"], ensure_ascii=False, indent=1)
    gsp = game / "style.json"
    if gsp.exists():
        gs = json.loads(gsp.read_text(encoding="utf-8"))
        ui += "\n本游戏风格（学自参考游戏，优先于上面的默认配色）：" + json.dumps({k: gs.get(k) for k in ("art_style", "mood", "ui_style", "props_style", "ui_palette")}, ensure_ascii=False) + "\n运行时已按 ui_palette 设置 CSS 变量，HUD/面板自动跟随，不要自己写颜色。"
    scene_note = ("本游戏已生成专属竖屏背景图，注入后 BF_ASSETS.__scene = {portrait: 'url'}；按 ui.background 用法铺满 #bg。"
                  if local_assets.get("__scene") else "本游戏暂无背景图：用 ui.palette.bg 到 #2a1d14 的径向渐变 + 暗角做背景，不要纯色。")
    lesson_note = ""
    if prd.get("workshop") == "cooking-lesson":
        L = prd.get("lesson", {})
        lesson_note = ("\n# 厂房 01 · 教学课模式（必须）\n"
            "这是一节做菜教学课，不是打分竞速。用 boot(game, { lesson: <下面的 lesson 对象>, ... }) 开启运行时教学课模式：首页自动变菜谱卡；每步开始调用 rt.lessonStep(i)；"
            "该步结束调用 rt.stepDone(i, accuracy0_100)（对错反馈与计分由运行时用工艺包原话完成）；全部步骤后调用 rt.lessonOver()（星级 + 你学会了卡）。\n"
            "硬规则：没有命数（不要调用 rt.setLives 扣命）；一次只有一个需处理的物件；步骤间 1–2 秒过场；每步有超时（该步窗口的 2.5 倍），超时按 0 分进入下一步；整课 ≤90 秒必然结束；"
            "步骤 1 是热身：仿真放慢由运行时负责，你只需把它的窗口设为正常 2 倍。\n"
            "准确度算法按每步 kind：timing=|操作时刻−窗口中点| 线性映射到 100→0；degree=状态进度落在停手线±δ 满分、过头线性扣；count=目标次数±1 满分。\n"
            "targets 每步只返回当前该操作的那一个物件，带 hint（用 do_short/stop_cue 写成人话），state 里的 lesson 由运行时维护。\n"
            "lesson 对象（原样传给 boot）：" + json.dumps(L, ensure_ascii=False)[:3000] + "\n")
    lay = local_assets.get("__layout")
    layout_note = (f"布局锚点（背景图里真实画出的容器/轨道，坐标为背景图 0–1 归一化）：{json.dumps(lay, ensure_ascii=False)}\n"
                   "物理硬规则：所有可点物件只能出现在这些锚点上（slots：中心对齐锚点中心、直径≈锚点半径×1.8；path：底边贴轨道线沿线运动）。"
                   "检验器会采样 target 位置，离锚点太远直接 FAIL。'冒出'动画在锚点内从 scale 0→1 并带小幅上抛落回，不许凭空出现在半空。"
                   if lay else "本游戏没有布局锚点：把物件放在背景里合理的台面高度（画面 45%–70%），不要悬在空中。")
    local_list = {k: v for k, v in local_assets.items() if k != "__scene"}
    return f"""你是黑灯工厂的游戏实现者。你的产物只会被机器检验，没有人看代码，所以：只做 PRD 写明的事，不发挥；宁可简单也要能跑。
平台：HTML5 + three.js r170 + 共享运行时 bf-runtime.js（stage/相机/HUD/面板/契约/资源加载/阴影/反馈全部由运行时负责）。你只写 game.js 里的玩法对象，index.html 用固定模板。只输出两个文件。

# 调试契约（检验器只认它，缺一项直接 FAIL）
{contract}

# 硬性规定（静态扫描 + 真浏览器 + 机器人）
{json.dumps(rules, ensure_ascii=False, indent=1)}

# 机器人怎么玩（你的游戏必须让它能得分并能结束）
- 机器人只读 __bf.state()，只发真实鼠标 pointerdown/click 到 target 的 (x,y) 中心。target 的 w/h 在手机视口下至少 60px，命中判定要宽松（包围球/包围盒，不要精确到 mesh 面）。
- 机器人得到 target_score 分后停手，等游戏自然结束；不输入时 60 秒仿真内必须进入 over。
- 同一个 seed、无输入，两局的结束时间必须完全一致：所有随机只用 seed 派生的 rng，所有时间只用固定步长累计，禁止 Date.now/Math.random/performance.now 参与逻辑。
- reset(seed) 后 phase 必须是 'menu'，menu 下点任意位置 = start()。

# 素材
window.BF_ASSETS 形如 {{"蘑菇": ["../../assets/食物/蘑菇_切块1.png", ...]}}，键是物件名。有贴图时用 PlaneGeometry + MeshBasicMaterial(map, transparent, alphaTest:0.05) 的面片；没有贴图（为空对象）时用带颜色的几何体占位。每种可点物件的 kind 必须写成 `kind: '中文名'` 字面量，且名字从这张表里选：{manifest_names}
不要 fetch/XHR 任何文件，不要加载 manifest；只用 BF_ASSETS 给的路径。加载失败也要让 ready 变 true（onError 里 resolve）。

{lesson_note}
# 画面与 UI 规范（用户终审最在意的部分；违反 ui.forbidden 会被视觉评审打回）
{ui}
{scene_note}
{layout_note}
专属素材（注入后 BF_ASSETS 的键，值是图片 URL 数组）：{json.dumps(local_list, ensure_ascii=False)}
所有可点物件用 rt.sprite(kind, size) 创建（运行时负责贴图/占位/阴影/受光）；target 在手机上 w/h ≥ 90px。

# 骨架
{SKELETON}

# {INDEX_TEMPLATE}

# 输出格式（严格，不要在文件外写解释）
=== FILE: index.html ===
<完整内容>
=== FILE: game.js ===
<完整内容>
=== END ===
"""


def parse_files(text):
    files = {m.group(1): m.group(2) for m in FILE_RE.finditer(text + ("\n=== END ===" if "=== END ===" not in text else ""))}
    for k, v in list(files.items()):
        v = v.strip("\n")
        if v.startswith("```"):
            v = v.split("\n", 1)[1]
            if v.rstrip().endswith("```"): v = v.rstrip()[:-3]
        files[k] = v.rstrip() + "\n"
    return files


def run_verify(game_dir):
    r = subprocess.run([sys.executable, str(ROOT / "factory/verify.py"), str(game_dir)], capture_output=True, text=True)
    verdict = next((l.split(":", 1)[1].strip() for l in r.stdout.splitlines() if l.startswith("VERDICT:")), "ERROR")
    rep_line = next((l for l in r.stdout.splitlines() if l.startswith("报告:")), "")
    report = {}
    if rep_line:
        p = Path(rep_line.split(":", 1)[1].strip()) / "report.json"
        if p.exists(): report = json.loads(p.read_text(encoding="utf-8"))
    return verdict, report, r.stdout[-2000:] + r.stderr[-1000:]


def feedback_message(report, raw):
    fails = report.get("fails") or [raw]
    extra = []
    for vp in report.get("viewports", []):
        if vp.get("page_errors"): extra.append(f"[{vp['name']}] 未捕获异常: {vp['page_errors'][:3]}")
        if vp.get("console_errors"): extra.append(f"[{vp['name']}] console.error: {vp['console_errors'][:3]}")
        if vp.get("failed_requests"): extra.append(f"[{vp['name']}] 失败请求: {vp['failed_requests'][:3]}")
        for g in vp.get("games", []):
            extra.append(f"[{vp['name']}] seed={g['seed']} 终局 {json.dumps(g['final'], ensure_ascii=False)[:300]}")
    return ("检验器裁决 FAIL。逐条失败项：\n- " + "\n- ".join(fails) + ("\n\n补充证据：\n- " + "\n- ".join(extra) if extra else "")
            + "\n\n请找机制层真因后修复，重新输出两个完整文件（同样的 === FILE 格式），不要只给 diff，不要解释。")


def game_style_of(game, style):
    sp = game / "style.json"
    if not sp.exists(): return style["scene"]["anchor_zh"], style["ui"]
    gs = json.loads(sp.read_text(encoding="utf-8"))
    anchor = f"参考游戏风格：{gs.get('art_style')}；{gs.get('render')}；色调 {gs.get('palette_desc') or gs.get('palette')}；氛围 {gs.get('mood')}；UI {gs.get('ui_style')}；道具 {gs.get('props_style')}；背景 {gs.get('background_style')}。（模仿风格，不复制素材）"
    ui = dict(style["ui"]); ui["palette"] = gs.get("ui_palette", ui.get("palette")); ui["style_note"] = f"本游戏风格已改为学自参考（{gs.get('art_style')}），不要再按暗黑写实/金色描边评判；配色以 ui_palette 为准"
    return anchor, ui


def visual_review(game, report, style):
    """让 vision 模型对照 style.scene/ui 看 playing/over 截图，产出 1–5 分和具体不符项。建议性：写入 games/<id>/visual-review.json。"""
    rep_dir = ROOT / "reports" / f"{game.name}-{report['ts']}"
    shots = [rep_dir / f"{vp['name']}-{k}.png" for vp in report["viewports"] for k in ("playing", "over")]
    shots = [s for s in shots if s.exists()][:4]
    if not shots: return
    prompt = ("你是游戏美术总监。下面是一款 HTML5 小游戏的实机截图（手机竖屏和桌面横屏，游玩中与结算）。"
              "对照【风格锚点】和【UI 规范】逐项检查，只输出 JSON：{\"score\":1-5, \"pass\":bool, \"issues\":[{\"where\":\"...\",\"problem\":\"...\",\"fix\":\"具体可执行的改法\"}], \"good\":[\"...\"]}。"
              "score≥4 才算 pass。不要客气，纯色背景、裸 HUD、卡通配色、占位几何体都要指出；但只提贴图面片 + CSS 能做到的改法，不要要求 3D 建模。\n【评审优先级】" + style["ui"].get("review_focus", "")
              + "\n\n【风格锚点】" + game_style_of(game, style)[0]
              + "\n【UI 规范】" + json.dumps(game_style_of(game, style)[1], ensure_ascii=False))
    text = llm.chat_vision(prompt, [str(s) for s in shots], role="vision", max_tokens=8000, json_mode=True, tag=f"visual:{game.name}")
    s = text.strip()
    if s.startswith("```"): s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    review = json.loads(s); review["shots"] = [str(x.relative_to(ROOT)) for x in shots]; review["ts"] = report["ts"]
    (game / "visual-review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    (game / "visual-review-log.jsonl").open("a", encoding="utf-8").write(json.dumps({"ts": report["ts"], "score": review.get("score"), "n_issues": len(review.get("issues", []))}, ensure_ascii=False) + "\n")
    print(f"  视觉评审 {review.get('score')}/5 {'✓' if review.get('pass') else '✗'}；问题 {len(review.get('issues', []))} 条 → {game.name}/visual-review.json")
    for it in review.get("issues", [])[:5]: print(f"    · {it.get('where')}: {it.get('problem')[:80]}")
    return review


def visual_feedback(review):
    lines = [f"- [{it.get('where')}] 问题：{it.get('problem')}\n  改法：{it.get('fix')}" for it in review.get("issues", [])]
    return ("技术检验已 PASS，但美术总监的视觉评审只给 " + str(review.get("score")) + "/5（要求 ≥4）。逐条问题与改法：\n" + "\n".join(lines)
            + "\n\n要求：在不破坏任何技术约束（调试契约、固定步长、可复现、零报错、target 尺寸、60 秒内可自然结束）的前提下修正画面与 UI；"
              "玩法数值不要动。重新输出两个完整文件（同样的 === FILE 格式），不要解释。")


def files_as_message(game):
    return "".join(f"=== FILE: {n} ===\n{(game / n).read_text(encoding='utf-8')}\n" for n in ("index.html", "game.js")) + "=== END ==="


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_dir"); ap.add_argument("--attempts", type=int, default=4)
    ap.add_argument("--model", default=None); ap.add_argument("--max-tokens", type=int, default=30000)
    ap.add_argument("--no-inject", action="store_true", help="PASS 后不注入真实素材")
    ap.add_argument("--review-only", action="store_true", help="不生成，只对最近一次检验报告跑视觉评审")
    ap.add_argument("--visual-attempts", type=int, default=2, help="视觉评审不达标时回灌重生成的最大轮数（0=只建议不门禁）")
    ap.add_argument("--visual-pass", type=int, default=4, help="视觉评审通过分")
    ap.add_argument("--continue", dest="cont", action="store_true", help="从游戏目录现有 index.html/game.js 起步（跳过首轮生成，直接检验+评审+修）")
    ap.add_argument("--fidelity", action="store_true", help="技术 PASS 后跑保真比对（与 research.json 的参考视频），分 < --fidelity-pass 时把差异回灌")
    ap.add_argument("--fidelity-pass", type=int, default=75); ap.add_argument("--fidelity-attempts", type=int, default=2); ap.add_argument("--ref-title", default=None)
    a = ap.parse_args()
    if a.review_only:
        game = Path(a.game_dir).resolve()
        style = json.loads((ROOT / "specs/style.json").read_text(encoding="utf-8"))
        reps = sorted((ROOT / "reports").glob(f"{game.name}-*/report.json"))
        if not reps: raise SystemExit("没有检验报告")
        visual_review(game, json.loads(reps[-1].read_text(encoding="utf-8")), style); return
    game = Path(a.game_dir).resolve()
    prd = json.loads((game / "prd.json").read_text(encoding="utf-8"))
    contract = (ROOT / "specs/debug-contract.md").read_text(encoding="utf-8")
    rules = json.loads((ROOT / "specs/rules/h5-hard-rules.json").read_text(encoding="utf-8"))
    mp = ROOT / "assets/manifest.json"; manifest = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}   # 公共素材库可选
    names = sorted(n for cat in manifest.values() for n in cat)
    style = json.loads((ROOT / "specs/style.json").read_text(encoding="utf-8"))
    lp = game / "assets/manifest.json"
    local_assets = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
    local_flat = {"__scene": local_assets.get("__scene", {})}
    lp2 = game / "assets/layout.json"
    if lp2.exists():
        _l = json.loads(lp2.read_text(encoding="utf-8")); local_flat["__layout"] = {k: _l[k] for k in ("type", "slots", "points", "width", "img_w", "img_h") if k in _l}
    for cat, names_ in local_assets.items():
        if cat not in ("__scene", "__layout"):
            for n_, states in names_.items(): local_flat[n_] = [f for s in states.values() for f in s]
    log = game / "gen-log.jsonl"
    attempts_dir = game / "attempts"

    messages = [{"role": "system", "content": build_system(prd, contract, rules, names, style, local_flat, game)},
                {"role": "user", "content": "PRD 如下，按它实现：\n" + json.dumps(prd, ensure_ascii=False, indent=1)}]
    verdict = "FAIL"; visual_used = 0; final_review = None; best_pass = None; fidelity_used = 0; last_fails = None
    total = a.attempts + a.visual_attempts + (a.fidelity_attempts if a.fidelity else 0)
    for n in range(1, total + 1):
        t0 = time.time()
        if a.cont and n == 1 and (game / "game.js").exists():
            print(f"\n=== 尝试 {n} · 沿用现有代码，直接检验 ===")
            text = files_as_message(game)
        else:
            print(f"\n=== 尝试 {n}/{total} · 模型 {a.model or llm.DEFAULTS['code']} ===")
            try:
                text = llm.chat(messages, role="code", model=a.model, max_tokens=a.max_tokens, tag=f"gen:{game.name}:{n}")
            except RuntimeError as e:
                print("  ✗", e)
                if "截断" in str(e):
                    messages.append({"role": "user", "content": f"上一次输出因过长被截断（{e}）。请精简：去掉注释和重复代码，game.js 控制在 400 行内，重新完整输出两个文件。"})
                log.open("a", encoding="utf-8").write(json.dumps({"attempt": n, "verdict": "TRUNCATED" if "截断" in str(e) else "LLM_ERROR", "err": str(e)[:200], "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
                continue      # 网络/超时：不追加消息，原样重试
        files = parse_files(text)
        messages.append({"role": "assistant", "content": text})
        if not {"index.html", "game.js"} <= set(files):
            fb = f"输出格式错误：只解析到 {list(files)}，需要 index.html 和 game.js 两个文件，用 === FILE: 名 === 分隔，以 === END === 结尾。重新完整输出。"
            print("  ✗", fb); messages.append({"role": "user", "content": fb})
            log.open("a", encoding="utf-8").write(json.dumps({"attempt": n, "verdict": "FORMAT", "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
            continue
        adir = attempts_dir / str(n); adir.mkdir(parents=True, exist_ok=True)
        for k, v in files.items():
            (game / k).write_text(v, encoding="utf-8"); (adir / k).write_text(v, encoding="utf-8")
        def _inject():
            inj = subprocess.run([sys.executable, str(ROOT / "factory/inject_assets.py"), str(game)], capture_output=True, text=True)
            return inj.returncode == 0, (inj.stdout + inj.stderr).strip()[-300:]
        has_local = (game / "assets/manifest.json").exists()
        if has_local and not a.no_inject:
            ok_inj, msg = _inject()                       # 有专属素材/锚点：先注入再检验（占位阶段没有锚点，物理层必然误判）
            if not ok_inj:
                verdict, report, raw, stage = "FAIL", {"fails": ["素材注入失败（PRD assets 的物件名在 manifest 里找不到？）: " + msg]}, "", "inject"
            else:
                verdict, report, raw = run_verify(game); stage = "with-assets"
        else:
            verdict, report, raw = run_verify(game); stage = "placeholder"
            if verdict == "PASS" and not a.no_inject:
                ok_inj, msg = _inject()
                if not ok_inj:
                    verdict, report, raw, stage = "FAIL", {"fails": ["素材注入失败: " + msg]}, "", "inject"
                else:
                    verdict, report, raw = run_verify(game); stage = "with-assets"
        fails = report.get("fails", [])
        print(f"  {stage} → {verdict}  ({time.time()-t0:.0f}s)"); [print("   ✗", f) for f in fails[:8]]
        log.open("a", encoding="utf-8").write(json.dumps({"attempt": n, "stage": stage, "verdict": verdict, "fails": fails,
                                                           "report": report.get("ts"), "secs": round(time.time() - t0), "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
        if verdict == "PASS":
            best_pass = n   # 记住最近一次技术 PASS 的尝试，后面视觉修正把它改坏时可回滚
            try:
                final_review = visual_review(game, report, style)
            except Exception as e:
                print("  ⚠ 视觉评审失败（按通过处理）:", str(e)[:200]); final_review = None
            if final_review and (final_review.get("score") or 0) < a.visual_pass and visual_used < a.visual_attempts:
                visual_used += 1
                messages.append({"role": "user", "content": visual_feedback(final_review)})
                shutil.copytree(game, attempts_dir / f"{n}-visual-pass", dirs_exist_ok=True, ignore=shutil.ignore_patterns("attempts", "assets"))
                continue
            if a.fidelity and (game / "research.json").exists():
                cmd = [sys.executable, str(ROOT / "factory/fidelity.py"), str(game)] + (["--ref-title", a.ref_title] if a.ref_title else [])
                r = subprocess.run(cmd, capture_output=True, text=True)
                line = next((l for l in r.stdout.splitlines() if l.startswith("FIDELITY:")), None)
                fscore = int(line.split(":")[1]) if line else None
                if fscore is None:
                    (game / "fidelity-run.log").write_text(r.stdout[-4000:] + "\n--- stderr ---\n" + r.stderr[-4000:], encoding="utf-8")
                    print("  ⚠ 保真比对没有返回分数，原始输出见 games/%s/fidelity-run.log" % game.name)
                fid = json.loads((game / "fidelity.json").read_text(encoding="utf-8")) if (game / "fidelity.json").exists() else {}
                print(f"  保真比对 {fscore}/100（参考 {fid.get('ref_title', '?')}）· 差异 {len(fid.get('diffs', []))} 条")
                for d in fid.get("diffs", [])[:4]: print(f"    · [{d.get('severity')}] {d.get('aspect')}: {str(d.get('fix'))[:90]}")
                if fscore is not None and fscore < a.fidelity_pass and fidelity_used < a.fidelity_attempts:
                    fidelity_used += 1
                    layout_note = ""
                    lf = fid.get("layout_fix")
                    if lf and lf.get("count") and (prd.get("layout") or {}).get("count") != lf.get("count"):
                        # 布局差异回到 PRD 与背景：改 layout → 重生背景+锚点 → 重注入
                        prd["layout"] = {"type": lf.get("type", "slots"), "count": int(lf["count"]), "zh": lf.get("zh", ""), "en": lf.get("en", "")}
                        (game / "prd.json").write_text(json.dumps(prd, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"  ↺ 布局差异路由到 PRD/背景：layout → {prd['layout']['type']} × {prd['layout']['count']}，重生成背景与锚点…")
                        r2 = subprocess.run([sys.executable, str(ROOT / "factory/make_assets.py"), str(game), "--only", "bg", "--force"], capture_output=True, text=True)
                        print("    " + "\n    ".join(l for l in r2.stdout.splitlines() if "背景" in l or "复核" in l or "提取" in l)[:600])
                        subprocess.run([sys.executable, str(ROOT / "factory/inject_assets.py"), str(game)], capture_output=True, text=True)
                        lp3 = game / "assets/layout.json"
                        if lp3.exists():
                            _l = json.loads(lp3.read_text(encoding="utf-8")); local_flat["__layout"] = {k: _l[k] for k in ("type", "slots", "points", "width", "img_w", "img_h") if k in _l}
                        layout_note = f"\n注意：布局已按参考改为 {prd['layout']['type']} × {prd['layout']['count']}，背景与锚点已重生成；代码必须只用 rt.anchors() 得到的锚点数量与位置，不要写死数量。新锚点：{json.dumps(local_flat.get('__layout'), ensure_ascii=False)[:800]}"
                    lines = [f"- [{d.get('severity')}] {d.get('aspect')}（{d.get('route', 'code')}）：参考「{d.get('ref')}」，我们「{d.get('ours')}」 → 改法：{d.get('fix')}" for d in fid.get("diffs", []) if d.get("route", "code") != "assets"]
                    messages.append({"role": "user", "content": f"技术检验已 PASS。但与参考游戏《{fid.get('ref_title')}》的复刻保真比对只有 {fscore}/100（要求 ≥{a.fidelity_pass}）。逐项差异与改法：\n" + "\n".join(lines) + layout_note
                                     + "\n\n要求：让机制与体验逼近参考（布局、动词、节奏、状态序列、HUD、反馈、失败态），美术不用像。保持全部技术约束（契约、固定步长、可复现、零报错、target 尺寸、60 秒内自然结束、锚点物理）。重新输出两个完整文件（同样的 === FILE 格式），不要解释。"})
                    shutil.copytree(game, attempts_dir / f"{n}-fidelity-pass", dirs_exist_ok=True, ignore=shutil.ignore_patterns("attempts", "assets", "play"))
                    continue
            break
        if n >= total: break
        fb = feedback_message(report, raw)
        if fails and fails == last_fails:   # 同一组失败连续出现：升级提示，逼它换思路
            fb += ("\n\n⚠ 这组失败和上一轮完全相同，说明上一轮的改法没有触及真因。请：1) 逐条对照失败样本里的坐标与偏移，找到产生该坐标的那一行代码；"
                   "2) 如果是放置问题，改用运行时提供的 rt.placeInSlot / sp.setFoot(rt.pathAt(u))，不要手算；3) 只改必要的地方，不要重写无关部分（输出过长会被截断）。")
        last_fails = list(fails)
        messages.append({"role": "user", "content": fb})
    if verdict != "PASS" and best_pass is not None:   # 视觉修正把能跑的版本改坏了：回滚到最后一次技术 PASS
        for k in ("index.html", "game.js"):
            src = attempts_dir / str(best_pass) / k
            if src.exists(): (game / k).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run([sys.executable, str(ROOT / "factory/inject_assets.py"), str(game)], capture_output=True, text=True)
        print(f"  ↩ 最后一轮 FAIL，已回滚到尝试 {best_pass}（最近一次技术 PASS）")
        log.open("a", encoding="utf-8").write(json.dumps({"attempt": n, "verdict": "ROLLBACK", "to": best_pass, "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
        verdict = "PASS"
    vs = f" · 视觉 {final_review.get('score')}/5" if final_review else ""
    print(f"\nGENERATE: {verdict}{vs}")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
