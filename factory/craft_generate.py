"""手作模拟品类生成环：一句话题材 → LLM 按模块契约写 games/<id>/game.js（引擎在 vendor/craft/）→ craft_verify 驾驭一整局
（每步穿模/组装/物理 + 结算出分）→ 驳回报告回灌重试，直到 PASS 或达上限。可选 --grade 再跑外部模型盲测。
用法: craft_generate.py "豆腐脑摊：舀豆花、浇卤、加配料" --id doufunao [--attempts 4] [--vision]
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402

CONTRACT = (ROOT / "specs/craft-module-contract.md").read_text(encoding="utf-8")
EXAMPLE = (ROOT / "vendor/craft/examples/tanghulu.js").read_text(encoding="utf-8")
RULES = json.loads((ROOT / "specs/rules/h5-hard-rules.json").read_text(encoding="utf-8")).get("craft_sim", {})
SYSTEM = f"""你是黑灯工厂的手作模拟游戏程序员。只输出一个文件的内容：games/<id>/game.js（ES module，默认导出一个模块对象），用 ```js 代码块包住，不要任何别的文字。
引擎已经写好（three.js r170 + vendor/craft/），你只写这一个模块。契约如下，逐条遵守：

{CONTRACT}

品类硬性规定（JSON）：
{json.dumps(RULES, ensure_ascii=False)}

参考模块（结构、体量、写法都照它；不要抄它的题材）：
```js
{EXAMPLE}
```
"""


def extract_js(text):
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def verify(game: Path):
    js = ROOT / "reports/craft" / game.name / "verify.json"; js.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(ROOT / "factory/craft_verify.py"), str(game), "--json", str(js)], capture_output=True, text=True)
    R = json.loads(js.read_text(encoding="utf-8")) if js.exists() else {"pass": False, "errors": [r.stderr[-800:]], "clips": [], "clip_summary": []}
    return R, (r.stdout + r.stderr)[-2000:]


def feedback(R, log):
    lines = []
    for e in R.get("errors", []): lines.append(f"- 运行错误：{e}")
    for c in R.get("clip_summary", []): lines.append(f"- 穿模/组装/物理违规（每帧检验）：{c}")
    for h in R.get("text_too_long", []): lines.append(f"- 提示文字太长：{h}")
    if R.get("score") is None and not R.get("errors"): lines.append("- 没走到结算出分")
    return "\n".join(lines) or log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("one_liner"); ap.add_argument("--id", required=True); ap.add_argument("--attempts", type=int, default=4)
    ap.add_argument("--model", default=None); ap.add_argument("--grade", action="store_true", help="PASS 后再跑 craft_grade 盲测")
    a = ap.parse_args()
    game = ROOT / "games" / a.id; game.mkdir(parents=True, exist_ok=True)
    (game / "index.html").write_text((ROOT / "vendor/craft/template.html").read_text(encoding="utf-8").replace("{{TITLE}}", a.one_liner[:20]), encoding="utf-8")
    log = game / "craft-gen-log.jsonl"
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"题材：{a.one_liner}\n模块 id 必须是 '{a.id}'。先在心里定：这家店叫什么、3–5 道真实的工序各是什么手上动作、每道的隐形评分标准是什么（分量/时机/手法，要有出处的常识）、场景放哪几件陈设。然后直接写模块。**篇幅硬限制：整个模块 ≤ 320 行、≤ 40KB**，超了就删陈设和花活，先保证工序跑通；不要在代码块外写任何解释。"}]
    for n in range(1, a.attempts + 1):
        t0 = time.time(); text = None
        for extra in ({"reasoning": {"effort": "low"}}, None):   # 推理 token 也算输出预算：先要求少想多写，不支持的模型再退回默认
            try: text = llm.chat(messages, role="code", model=a.model, max_tokens=60000, tag=f"craft:{a.id}:{n}", grow=False, extra=extra); break
            except RuntimeError as e:
                print("  ↻", str(e)[:120], flush=True)
                if extra is None: raise
        code = extract_js(text); (game / "game.js").write_text(code, encoding="utf-8"); (game / "attempts").mkdir(exist_ok=True); (game / "attempts" / f"{n}.js").write_text(code, encoding="utf-8")
        R, out = verify(game)
        rec = {"attempt": n, "pass": R.get("pass"), "score": R.get("score"), "errors": R.get("errors", [])[:6], "clips": R.get("clip_summary", [])[:6], "lines": code.count("\n"), "seconds": round(time.time() - t0, 1)}
        log.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n== 第 {n} 次：{'PASS' if R.get('pass') else 'FAIL'} · {rec['lines']} 行 · 结算 {R.get('score')} · {rec['seconds']}s"); print(out.strip()[-1200:], flush=True)
        if R.get("pass"): break
        messages.append({"role": "assistant", "content": text}); messages.append({"role": "user", "content": "检验器驳回，逐条修掉后重新输出**完整**的 game.js（还是只要一个代码块）：\n" + feedback(R, out)})
    else:
        print("CRAFT-GEN: FAIL"); sys.exit(1)
    print(f"CRAFT-GEN: PASS → games/{a.id}/index.html（python3 factory/serve.py 后打开 http://127.0.0.1:8765/games/{a.id}/index.html）")
    if a.grade:
        subprocess.run([sys.executable, str(ROOT / "factory/craft_grade.py"), "--cand", f"games/{a.id}", "--theme", a.id])


if __name__ == "__main__":
    main()
