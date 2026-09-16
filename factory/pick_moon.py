#!/usr/bin/env python3
"""选月亮：把 research.json 里链接已核实（verified/replaced）的竞品 + 视频观察摘要交给 trinity（三体迭代）裁决：
哪一个是"机制最近且最热门"的复刻参考。结果写回 research.json 的 moon_pick（含 trinity 的机器判定行，UNVERIFIED 要如实保留）。
用法: .venv/bin/python factory/pick_moon.py games/<id>
"""
import json, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    game = Path(sys.argv[1]).resolve(); rp = game / "research.json"
    r = json.loads(rp.read_text(encoding="utf-8"))
    moons = [m for m in r.get("moons", []) if m.get("link_status") in ("verified", "replaced")]
    if not moons:
        print("PICK: 无可用竞品（链接都未核实），先跑 verify_links.py"); return
    vids = [v for v in r.get("videos", []) if v.get("relevant", True)]
    # 视频里学到的游戏也是候选（它们有实机观察，往往比网页找到的更准）
    names = {m["name"] for m in moons}
    for v in vids:
        title = (v.get("title") or "").split("|")[0].split(":")[0].strip()[:40]
        if title and not any(title.lower() in n.lower() or n.lower() in title.lower() for n in names):
            moons.append({"name": title, "platform": "YouTube 实机", "popularity": "视频观察", "core_loop": str(v.get("core_loop", ""))[:80], "link_title": "实机视频已抽帧", "url": v.get("video"), "from_video": True})
    cand = "；".join(f"{chr(65+i)}) {m['name']}（{m.get('platform','')}；热度依据：{m.get('popularity') or '未查到'}；机制：{m.get('core_loop','')[:60]}；链接已核实：{m.get('link_title','')[:30]}）" for i, m in enumerate(moons))
    vdesc = "；".join(f"视频《{v.get('title','')[:30]}》观察：{str(v.get('core_loop',''))[:80]}" for v in vids[:2])
    q = (f"题材：「{r.get('topic','')}」。要选一个'月亮'（机制最接近且当下最热门的真实竞品）作为复刻参考。候选（链接均已 HTTP 核实页面存在）：{cand}。"
         f"另有实机视频观察：{vdesc or '无'}。"
         "问题：1) 哪一个最该当月亮，为什么；2) 候选里有没有你认为其实不是同机制、应剔除的；3) 是否存在更热门且机制更近的真实游戏（不确定就说不确定，不要编名字）。"
         "最后单独一行输出 PICK: <候选字母>")
    t0 = time.time()
    p = subprocess.run(["trinity", "--domain", "游戏产品", "--timeout", "240", q], capture_output=True, text=True)
    out = p.stdout + p.stderr
    verdict = next((l.strip() for l in out.splitlines() if l.strip().startswith("机器判定")), "")
    pick = re.search(r"PICK:\s*([A-Z])", out)
    chosen = moons[ord(pick.group(1)) - 65]["name"] if pick and 0 <= ord(pick.group(1)) - 65 < len(moons) else None
    r["moon_pick"] = {"chosen": chosen, "trinity_verdict": verdict, "exit_code": p.returncode, "answer": out.strip()[-3000:], "ts": time.strftime("%F %T"), "secs": round(time.time() - t0)}
    for m in r.get("moons", []): m["is_moon"] = (m.get("name") == chosen)
    if chosen and not any(m.get("name") == chosen for m in r.get("moons", [])):   # 选中的是视频候选：补进 moons，链接就是视频
        vm = next(m for m in moons if m.get("name") == chosen); vm.update({"link_status": "verified", "evidence": "[视频抽帧]", "is_moon": True}); r["moons"].insert(0, vm)
    rp.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    (game / "research.md").open("a", encoding="utf-8").write(f"\n## 月亮裁决（trinity，{r['moon_pick']['ts']}）\n\n{out.strip()}\n")
    print(out.strip()[-1800:])
    print(f"\nPICK: {chosen or '未解析'} · {verdict or f'trinity 退出码 {p.returncode}'}")
    if p.returncode not in (0, 1): sys.exit(p.returncode)


if __name__ == "__main__":
    main()
