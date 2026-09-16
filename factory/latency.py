#!/usr/bin/env python3
"""发现延迟与复发度量：读 games/<id>/rounds.jsonl（ledger.py 写的），按"失败签名"统计——
  · 引入→发现：某条失败第一次红之前，最近一次引擎/工厂文件指纹变化是在几轮前（那次改动最可能是引入者）
  · 发现→修掉：从第一次红到之后第一次绿隔了几轮
  · 复发：同一签名绿了之后又红了几次（= 同一个毛病被绕过第二次）
签名 = 失败文案去掉数字、坐标、seed 后的骨架，所以"只完成 0/5 步"和"只完成 2/5 步"算同一条。
用法: .venv/bin/python factory/latency.py games/<id> [--kind verify|realism|all]
最后一行: LATENCY: <轮数> rounds · <签名数> signatures · <复发数> recurrences   （没有台账就打印 LATENCY: NO_LEDGER）
"""
import argparse, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

CODE_KEYS = [k for k in ledger.TRACKED]


def signature(msg: str):
    s = re.sub(r"\[(mobile|desktop)\]\s*", "", str(msg))
    s = re.sub(r"seed=\d+:?\s*", "", s)
    s = re.sub(r"[\d.]+%", "N%", s); s = re.sub(r"\(\d+,\s*\d+\)", "(x,y)", s); s = re.sub(r"\d+(\.\d+)?", "N", s)
    return s.strip()[:110]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("game_dir"); ap.add_argument("--kind", default="all")
    a = ap.parse_args(); g = Path(a.game_dir).resolve()
    rows = [r for r in ledger.load(g) if a.kind == "all" or r.get("kind") == a.kind]
    if not rows: print("LATENCY: NO_LEDGER（还没有 rounds.jsonl；跑一次 verify/realism 就有了）"); return
    # 每轮：代码指纹是否相对上一轮变了
    changed_at = []; prev = None
    for i, r in enumerate(rows):
        fp = {k: r.get("fp", {}).get(k) for k in CODE_KEYS}
        changed = prev is not None and fp != prev
        changed_at.append(i if (changed or i == 0) else changed_at[-1]); prev = fp
    sigs = {}
    for i, r in enumerate(rows):
        for f in (r.get("fails") or []):
            sigs.setdefault(signature(f), []).append(i)
    print(f"{g.name}: {len(rows)} 轮 · {len(sigs)} 种失败签名")
    print(f"{'首红轮':>6} {'引入→发现':>9} {'发现→绿':>8} {'复发':>4}  签名")
    recur_total = 0
    for sig, idxs in sorted(sigs.items(), key=lambda kv: kv[1][0]):
        first = idxs[0]; intro = changed_at[first]; detect = first - intro
        kind = rows[first].get("kind")                                   # 只拿同一种判官的后续轮当"绿"：realism 的红不能被 verify 的绿抵掉
        same = [j for j in range(first + 1, len(rows)) if rows[j].get("kind") == kind and rows[j].get("verdict") in ("PASS", "FAIL")]
        red = set(idxs); fixed = next((j for j in same if j not in red), None)
        to_green = (fixed - first) if fixed is not None else None
        # 复发：（同种判官）绿过之后再红
        recur = 0; seen_green = False
        for j in [first] + same:
            if j in red and seen_green: recur += 1; seen_green = False
            elif j not in red: seen_green = True
        recur_total += recur
        print(f"{first + 1:>6} {detect:>9} {str(to_green if to_green is not None else '未修'):>8} {recur:>4}  {sig}")
    print(f"LATENCY: {len(rows)} rounds · {len(sigs)} signatures · {recur_total} recurrences")


if __name__ == "__main__":
    main()
