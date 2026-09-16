#!/usr/bin/env python3
"""找月亮：给一句话题材做竞品/SOTA 调研（联网检索），产出 games/<id>/research.json + research.md。
用法: .venv/bin/python factory/research.py "一句话题材" --id my-game [--n 4]
每条结论带来源 URL，证据等级 [网页]；查不到的写 unanswerable，不许编。make_prd 会自动读取同目录的 research.json。
"""
import argparse, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402

Q_MOONS = ("题材：「{topic}」。请联网找出 {n} 款真实存在、机制最接近、**当下最热门**的手机/小程序/H5 小游戏：优先看近两年 App Store/Google Play/微信小游戏榜单排名、下载量、评分人数、热搜/视频播放量。"
           "按热度从高到低排列，每款给：名称、平台、热度依据（榜单名次/下载量/评分数，带数字）、核心循环一句话、美术风格一句话（卡通/写实/像素等与配色）、为什么它是这个题材的标杆、来源链接。只列有来源链接的，查不到就少列。")
Q_NUMBERS = ("以下几款游戏：{names}。请联网查它们公开可查的设计数值与规则：单局时长、目标出现间隔或节奏、命数/失败条件、难度如何随时间上升、连击/加分规则、首个付费点或激励视频出现的时机。"
             "每个数字都要附来源链接；查不到的明确写『未查到』，不要估算。")
Q_TRENDS = ("题材：「{topic}」。请联网查 2025–2026 年这类点击反应小游戏（微信小游戏 / 抖音小游戏 / 超休闲）的设计趋势：留住玩家的钩子、常见的失败设计、"
            "平均单局时长、竖屏 UI 惯例。每条附来源链接，查不到的不写。")
STRUCT = """把下面三段调研原文整理成 JSON（只输出 JSON）：
{"moons":[{"name":"","platform":"","url":"","popularity":"热度依据（带数字）","core_loop":"","art_style":"","why_moon":"","evidence":"[网页]"}],
 "numbers":[{"game":"","item":"","value":"","url":"","evidence":"[网页]"}],
 "insights":[{"text":"","url":"","evidence":"[网页]"}],
 "unanswerable":["原文里明确说未查到的项"]}
规则：只保留原文里带 URL 的条目；URL 原样复制；没有 URL 的条目丢进 unanswerable；不要补充原文没有的信息。

=== 竞品 ===
{moons}
=== 数值 ===
{numbers}
=== 趋势 ===
{trends}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic"); ap.add_argument("--id", required=True); ap.add_argument("--n", type=int, default=4)
    a = ap.parse_args()
    game = ROOT / "games" / a.id; game.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); cites = []
    print("① 找竞品…"); moons_txt, c1 = llm.chat_web(Q_MOONS.format(topic=a.topic, n=a.n), tag=f"research:{a.id}:moons"); cites += c1
    # 先把竞品名结构化出来，再拿真名去查数值（正则抓粗体会抓到"平台"这类标签）
    m0 = llm.chat_json([{"role": "user", "content": "从下面文字里抽出游戏名称列表，只输出 JSON {\"names\":[...]}，不要平台名和标签词：\n" + moons_txt}], role="cheap", max_tokens=500, tag=f"research:{a.id}:names")
    names = [n for n in m0.get("names", []) if 1 < len(n) < 40][: a.n] or [a.topic]
    print("② 查数值…", names); numbers_txt, c2 = llm.chat_web(Q_NUMBERS.format(names="、".join(names)), tag=f"research:{a.id}:numbers"); cites += c2
    print("③ 查趋势…"); trends_txt, c3 = llm.chat_web(Q_TRENDS.format(topic=a.topic), tag=f"research:{a.id}:trends"); cites += c3
    print("④ 结构化…")   # 分两次，避免一次输出过长被截断
    d1 = llm.chat_json([{"role": "user", "content": STRUCT.replace("{moons}", moons_txt).replace("{numbers}", numbers_txt).replace("{trends}", "（本次不处理）")}],
                       role="cheap", max_tokens=12000, tag=f"research:{a.id}:struct1")
    d2 = llm.chat_json([{"role": "user", "content": STRUCT.replace("{moons}", "（本次不处理）").replace("{numbers}", "（本次不处理）").replace("{trends}", trends_txt)}],
                       role="cheap", max_tokens=12000, tag=f"research:{a.id}:struct2")
    data = {"moons": d1.get("moons", []), "numbers": d1.get("numbers", []), "insights": d2.get("insights", [])[:12],
            "unanswerable": (d1.get("unanswerable", []) + d2.get("unanswerable", []))}
    # 防幻觉链接：URL 必须出现在联网检索的真实结果（citations）里，否则清空并标 unverified；之后由 verify_links.py 核实/替换
    real = {c["url"] for c in cites}
    for m in data["moons"]:
        u = m.get("url", "")
        if u and not any(u.rstrip("/") == r.rstrip("/") or u.rstrip("/") in r or r.rstrip("/") in u for r in real):
            m["url_claimed"] = u; m["url"] = ""; m["link_status"] = "unverified"
    print(f"   链接自检：{sum(1 for m in data['moons'] if m.get('url'))}/{len(data['moons'])} 个竞品链接出现在真实搜索结果里")
    data.update({"topic": a.topic, "ts": time.strftime("%F %T"), "citations": cites, "secs": round(time.time() - t0)})
    (game / "research.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# 找月亮：{a.topic}\n", f"_{data['ts']} · {len(data.get('moons', []))} 个竞品 · {len(data.get('numbers', []))} 条数值 · {len(data.get('insights', []))} 条趋势_\n",
          "## 竞品（月亮）\n"] + [f"- **{m['name']}**（{m['platform']}）：{m['core_loop']} — {m['why_moon']} [网页]({m['url']})" for m in data.get("moons", [])]
    md += ["\n## 数值\n"] + [f"- {x['game']} · {x['item']}：{x['value']} [网页]({x['url']})" for x in data.get("numbers", [])]
    md += ["\n## 趋势\n"] + [f"- {x['text']} [网页]({x['url']})" for x in data.get("insights", [])]
    md += ["\n## 未查到（不许编）\n"] + [f"- {x}" for x in data.get("unanswerable", [])]
    md += ["\n## 原文\n", "### 竞品\n" + moons_txt, "\n### 数值\n" + numbers_txt, "\n### 趋势\n" + trends_txt]
    (game / "research.md").write_text("\n".join(md), encoding="utf-8")
    print(f"RESEARCH: {len(data.get('moons', []))} 竞品 / {len(data.get('numbers', []))} 数值 / {len(data.get('insights', []))} 趋势 / {len(data.get('unanswerable', []))} 未查到 → games/{a.id}/research.md ({data['secs']}s)")
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "factory/verify_links.py"), str(game)])


if __name__ == "__main__":
    main()
