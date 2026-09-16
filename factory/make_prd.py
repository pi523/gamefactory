#!/usr/bin/env python3
"""一句话题材 → PRD（games/<id>/prd.json）。LLM 产 JSON → schema 校验 + 工厂规则 lint → 不合格把错误回灌重试。
用法: .venv/bin/python factory/make_prd.py "一句话题材" [--id my-game] [--attempts 3] [--build]
--build: PRD 通过后直接接 generate.py 生成并检验游戏（一句话 → 可玩游戏 一条命令）。
台账: games/<id>/prd-gen-log.jsonl。最后一行 PRD: PASS|FAIL（--build 时 generate.py 再打印 GENERATE: …）。
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

SYSTEM = """你是黑灯工厂的产品经理。把一句话题材写成一份 **机器可验收** 的 HTML5 小游戏 PRD，输出严格符合给定 JSON Schema 的 JSON 对象，不要输出任何解释。

写 PRD 的硬约束（违反会被 lint 打回）：
1. platform 固定 "html5"，engine 固定 "three"，style_ref 固定 "specs/style.json"，controls 是 tap/drag/swipe 的子集（点、拖、滑三种动词，机器人都会做：drag 拖到目的地，swipe 有方向）。
2. 每个动作对目标都必须是有益的：点/拖/滑一个目标应加分或推进，不能有"做错会扣分"的目标。**动词预算**：整局最多 3 个动词；开局前 5 个物件只用 1 个动词（通常是 tap），第 6 个物件起解锁第 2 个，第 12 个起解锁第 3 个；每个状态只允许一种操作；状态 ≤ 4。不要为了像参考而堆动作，普通人要能上手。检验器有一个'慢手机器人'（反应 0.7 秒、每秒一次操作）必须活过 40 秒并得 5 分。
3. 必须能自然结束：不输入时 60 秒仿真内一定进入 over（例如漏掉 N 个就失败、倒计时等）。end_conditions.lose 必填。
4. requirements 至少 6 条，id 用 R1、R2…；每条 evidence 只能是 [实测]/[网页]/[视频抽帧]/[推导]/[假设]。来自竞品实机视频观察的写 [视频抽帧]；来自调研且有来源的数值写 [网页]；自己推的写 [推导]；拍脑袋的写 [假设]；不许写 [实测]。
   check.layer：static（静态扫描能判）/ browser（真浏览器能判）/ bot（机器人玩能判）/ manual（只能人判，如手感、好看）。
   bot 层至少 3 条、browser 层至少 1 条；数值型规则（间隔、时长、命数）要写具体数字，不要写"合适的"。
5. assets：只写玩法层会出现的物件（可点目标、容器/盘子等前景道具）；会变化的物件写 states（如 ["生","半熟","金黄","焦"]，每个状态各生一张图），**环境类（传送带、灶台、桌面、墙、灯）一律不写进 assets，写进 scene_hint 由背景图承担**。最多 8 类，每个 count 2；优先选公共库已有物件名，题材需要的专属道具（如 传送带、烤架）也写进去，subject_en 写清楚形态；所有物件都会按题材重新生图，所以 name 要具体（如 牛排 而不是 肉）。
5b. 必须给 scene_type（从 schema 枚举里选一个最贴题材的餐饮场景）和 scene_hint（一句中文描述该场景的背景环境，不含任何玩法物件）。
5c. 必须给 layout：背景图就是关卡布局。type=slots 表示固定位置的容器（锅、格子、烤位、碗），count 为数量（≤9，推荐 4–9）；type=path 表示一条轨道（传送带、烤架长边、案板边），count 填 1。zh/en 描述数量、排列（如 3×3 网格）、透视（俯视 30–40°）。玩法物件只会出现在这些容器/轨道上，所以 core_loop 要与 layout 一致。
5d. 游戏只做手机竖屏 9:16，core_loop 和需求都按竖屏写。
5e. 必须各有一条需求写新手引导和情绪反馈，check.layer 用 browser。引导需求要写：每个状态下的一句人话提示（如'面糊定形了，滑一下翻面'）、热身期（开局前 6 秒不掉命，前 3 个物件窗口 ×2）、开局节奏（前 30 秒同时要处理的物件 ≤ 2，不操作时前 15 秒最多丢 1 命，供料区物件不因超时扣命）。情绪需求写题材化赞美词与里程碑。
6. moons（竞品/月亮）写 1–3 个真实存在的同机制游戏；若用户消息里带【调研结果】，只能从里面选并标 [网页] + source URL；没有调研时才用 [假设]。
7. core_loop 一段话讲清：场景里有什么、什么会出现、玩家点了发生什么、怎么算失败、难度怎么涨。
8. session_length_s 一局 15–120 秒之间。
9. id 用小写字母和连字符；title 中文；one_liner 原样复述用户的一句话。"""


def lint(prd, manifest_names):
    errs, warns = [], []
    if not prd.get("controls") or not set(prd["controls"]) <= {"tap", "drag", "swipe"}: errs.append("controls 只能是 tap/drag/swipe 的子集")
    reqs = prd.get("requirements", [])
    layers = [r.get("check", {}).get("layer") for r in reqs]
    if layers.count("bot") < 3: errs.append(f"bot 层需求至少 3 条，现在 {layers.count('bot')}")
    if layers.count("browser") < 1: errs.append("browser 层需求至少 1 条")
    if len(reqs) < 6: errs.append(f"requirements 至少 6 条，现在 {len(reqs)}")
    ids = [r.get("id") for r in reqs]
    if ids != [f"R{i}" for i in range(1, len(ids) + 1)]: errs.append(f"requirement id 必须是 R1..Rn 连续，现在 {ids}")
    if any(r.get("evidence") == "[实测]" for r in reqs): errs.append("没有做过实测，不许写 [实测]")
    text = json.dumps(prd, ensure_ascii=False)
    if not re.search(r"60|六十", text) and not re.search(r"(倒计时|计时|漏|miss|超时)", text):
        errs.append("看不出不输入时怎样在 60 秒内结束，请在 core_loop / end_conditions / requirements 里写明")
    sl = prd.get("session_length_s", {})
    if not (15 <= sl.get("min", 0) and sl.get("max", 999) <= 120): errs.append("session_length_s 需在 15–120 秒内")
    if len(prd.get("assets", [])) > 8: errs.append(f"assets 最多 8 类（包体限制），现在 {len(prd['assets'])}；挑最能代表题材的")
    if not prd.get("scene_hint"): errs.append("缺 scene_hint：一句话描述背景环境（灶台/案板/餐车…），不含任何玩法物件")
    if not prd.get("scene_type"): errs.append("缺 scene_type（餐饮场景类型，从枚举里选）")
    alltext = " ".join(r.get("text", "") for r in reqs)
    if len(prd.get("controls", [])) > 3: errs.append("controls 超过 3 个动词")
    if not re.search(r"解锁|逐步|先只|第 ?\d+ ?个物件", alltext + prd.get("core_loop", "")): errs.append("缺逐步解锁：开局前 5 个物件只用 1 个动词，之后再解锁其它动词，要写进 core_loop 或需求")
    if not re.search(r"引导|教学|提示玩家|新手", alltext): errs.append("缺新手引导需求（前几轮怎么教玩家点/拖/滑）")
    if not re.search(r"赞美|情绪|连击.*(大字|动画|文字)|鼓励|星级|反馈文案", alltext): errs.append("缺情绪反馈需求（玩得好时的大字/动画/星级何时触发、文案是什么）")
    lay = prd.get("layout") or {}
    if not lay: errs.append("缺 layout：背景即关卡布局，必须写 type/count/zh/en")
    elif lay.get("type") == "slots" and not (1 <= lay.get("count", 0) <= 9): errs.append("layout.count（slots）需在 1–9")
    for a in prd.get("assets", []):
        if a.get("name") not in manifest_names: warns.append(f"素材 {a.get('name')} 不在公共库，将由 make_assets 专属生成")
    return errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("one_liner"); ap.add_argument("--id", default=None); ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--model", default=None); ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    schema = json.loads((ROOT / "specs/prd.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    manifest = json.loads((ROOT / "assets/manifest.json").read_text(encoding="utf-8"))
    names = sorted(n for cat in manifest.values() for n in cat)

    research = None
    rp = ROOT / "games" / (a.id or "") / "research.json"
    if a.id and rp.exists():
        research = json.loads(rp.read_text(encoding="utf-8"))
        print(f"  读到调研：{len(research.get('moons', []))} 竞品 / {len(research.get('numbers', []))} 数值 / {len(research.get('insights', []))} 趋势")
    craft = None
    cp = ROOT / "games" / (a.id or "") / "craft-hints.json"
    if a.id and cp.exists():
        craft = json.loads(cp.read_text(encoding="utf-8"))
        print(f"  读到工艺包：{craft.get('dish')} · {len(craft.get('crafts', []))} 个工艺 / {len(craft.get('criteria', []))} 条判据")
    user = (f"一句话题材：{a.one_liner}\n" + (f"游戏 id 必须是：{a.id}\n" if a.id else "")
            + f"可用物件名（素材库已有）：{names}\n"
            + (("\n【调研结果（找月亮，均有来源）】\n" + json.dumps({k: research[k] for k in ("moons", "numbers", "insights", "unanswerable") if k in research}, ensure_ascii=False)
                + (("\n【视频抽帧观察（竞品实机录像，带时间戳）】\n" + json.dumps([{k: v.get(k) for k in ("title", "core_loop", "cadence", "hud", "feedback", "fail_state", "difficulty", "camera", "numbers")} for v in research.get("videos", []) if v.get("relevant", True)], ensure_ascii=False)
                    + "\n规则：来自视频的节奏/数值/HUD 惯例写进需求时 evidence 用 [视频抽帧]，text 末尾括注视频标题；视频里『未见』的不许当依据。") if research.get("videos") else "")
                + "\n规则：moons 只能从调研里 link_status 为 verified/replaced 的条目选（unverified 的不许用），is_moon=true 的那一个必须排第一并作为主要参考；evidence 写 [网页] 并把 url 原样填进 source；凡是数值来自调研的需求 evidence 写 [网页] 并在 text 末尾括注来源游戏名；调研里『未查到』的项不许编数字，用 [假设] 并给保守值。\n") if research else "")
            + (("\n【工艺包（真实做菜教学视频学来的，每条带时间戳）】\n" + json.dumps(craft, ensure_ascii=False)
                + "\n规则：玩法物件的 states 优先采用工艺的状态序列（phases label，可合并为 3–4 态）；动词优先采用 verbs；失败条件采用 fail_surface（做过头会怎样）；"
                  "\"该停手\"的视觉判据（stop_cue）写成一条 browser/manual 需求；这些需求的 evidence 写 [视频抽帧] 并在 text 末尾括注工艺名。\n") if craft else "")
            + (("\n【参考游戏的风格观察（模仿风格，不复制素材）】\n" + json.dumps([{"title": v.get("title"), "style": v.get("style")} for v in research.get("videos", []) if v.get("relevant", True) and v.get("style")], ensure_ascii=False)
                + "\n规则：PRD 必须带 style 字段 {art_style, render, mood, palette(hex 数组, 取 palette_kmeans 前 5 个并按风格调整), ui_style, props_style, background_style, style_prompt_en(60 词内英文生图风格提示), ui_palette{bg,panel,accent,text,danger}}，以最相关的参考为主；美术风格要**像参考**而不是默认暗黑写实。\n") if any(v.get("style") for v in research.get("videos", [])) else "")
            + f"\nJSON Schema：\n{json.dumps(schema, ensure_ascii=False)}")
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    prd = None; ok = False; game = None
    for n in range(1, a.attempts + 1):
        print(f"=== PRD 尝试 {n}/{a.attempts} ===")
        try:
            prd = llm.chat_json(messages, role="code", model=a.model, max_tokens=8000, tag=f"prd:{a.id or 'auto'}:{n}")
        except RuntimeError as e:
            messages.append({"role": "user", "content": f"{e}\n重新只输出 JSON。"}); print("  ✗", e); continue
        messages.append({"role": "assistant", "content": json.dumps(prd, ensure_ascii=False)})
        errs = [f"schema: {'/'.join(str(x) for x in e.absolute_path)}: {e.message}" for e in validator.iter_errors(prd)]
        lint_errs, warns = lint(prd, names) if not errs else ([], [])
        if research and not errs:
            if not any(m.get("evidence") == "[网页]" and m.get("source") for m in prd.get("moons", [])):
                lint_errs.append("有调研结果但 moons 没有一条 [网页] 带 source 的竞品")
            if sum(1 for r in prd.get("requirements", []) if r.get("evidence") == "[网页]") < 1 and research.get("numbers"):
                lint_errs.append("调研查到了数值，但没有任何需求引用 [网页]")
        errs += lint_errs
        gid = a.id or prd.get("id", "game")
        game = ROOT / "games" / gid; game.mkdir(parents=True, exist_ok=True)
        (game / "prd-gen-log.jsonl").open("a", encoding="utf-8").write(json.dumps({"attempt": n, "errors": errs, "warns": warns, "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
        for w in warns: print("  ⚠", w)
        if errs:
            for e in errs: print("  ✗", e)
            messages.append({"role": "user", "content": "PRD 未通过校验：\n- " + "\n- ".join(errs) + "\n修正后重新只输出完整 JSON。"})
            continue
        if a.id: prd["id"] = a.id
        (game / "prd.json").write_text(json.dumps(prd, ensure_ascii=False, indent=2), encoding="utf-8")
        # 每款游戏自己的风格文件：PRD.style 覆盖全局兜底（specs/style.json 的暗黑写实）
        g = json.loads((ROOT / "specs/style.json").read_text(encoding="utf-8"))
        base = {"art_style": "写实摄影级", "render": "3D 写实，暖色主光，柔和阴影", "mood": "暗黑写实/高端餐饮广告", "palette": ["#0d0b0a", "#2a1d14", "#c9a86a", "#f3ede4", "#e2574a"],
                "ui_style": "深色半透明面板+金色细描边", "props_style": "写实抠图", "background_style": "写实场景，清晰",
                "style_prompt_en": g["scene"]["anchor_en"], "ui_palette": {"bg": "#0d0b0a", "panel": "#14100e", "accent": "#c9a86a", "text": "#f3ede4", "danger": "#e2574a"}, "source": "default"}
        sty = dict(base); sty.update({k: v for k, v in (prd.get("style") or {}).items() if v}); sty["source"] = "reference" if prd.get("style") else "default"
        (game / "style.json").write_text(json.dumps(sty, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  风格：{sty['art_style'][:24]} · {sty['mood'][:16]}（{'学自参考' if sty['source']=='reference' else '兜底暗黑写实'}）")
        print(f"  ✓ {game.relative_to(ROOT)}/prd.json · {len(prd['requirements'])} 条需求 · {len(prd['assets'])} 类素材")
        ok = True; break
    print(f"PRD: {'PASS' if ok else 'FAIL'}")
    if not ok: sys.exit(1)
    if a.build:
        print("\n=== 生成专属素材 ===")
        subprocess.run([sys.executable, str(ROOT / "factory/make_assets.py"), str(game)])
        print("\n=== 生成代码 ===")
        r = subprocess.run([sys.executable, str(ROOT / "factory/generate.py"), str(game)])
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
