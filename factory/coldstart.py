#!/usr/bin/env python3
"""冷启动重跑：把 HEAD 干净地检出到临时 worktree（没有工作树里未提交的半截改动、没有 reports 缓存），
对指定游戏跑 N 次 verify.py，报成功率。不调 LLM，不花钱。
用法: .venv/bin/python factory/coldstart.py --n 5 --games tomato-egg,kungpao-chicken,braised-pork
输出: reports/coldstart-<ts>.json；每款一行 COLDSTART <game>: k/N；最后一行 COLDSTART: ALL_PASS|SOME_FAIL
"""
import argparse, json, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import ledger  # noqa: E402


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=5); ap.add_argument("--games", default="tomato-egg")
    ap.add_argument("--ref", default="HEAD", help="检出哪个提交（默认 HEAD）")
    a = ap.parse_args()
    games = [g.strip() for g in a.games.split(",") if g.strip()]
    ts = time.strftime("%Y%m%d-%H%M%S"); out = ROOT / "reports" / f"coldstart-{ts}.json"; out.parent.mkdir(exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "--short", a.ref], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    results = {g: [] for g in games}
    for i in range(a.n):
        wt = Path(tempfile.mkdtemp(prefix=f"bf-cold-{i}-"))
        shutil.rmtree(wt, ignore_errors=True)
        r = subprocess.run(["git", "worktree", "add", "--detach", str(wt), a.ref], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0: print("worktree 失败:", r.stderr.strip()[:200]); sys.exit(2)
        try:
            for g in games:
                t0 = time.time()
                v = subprocess.run([sys.executable, str(wt / "factory/verify.py"), str(wt / "games" / g), "--out", str(wt / "reports")], capture_output=True, text=True)
                verdict = next((l.split(":", 1)[1].strip() for l in v.stdout.splitlines() if l.startswith("VERDICT:")), "ERROR")
                fails = [l.strip() for l in v.stdout.splitlines() if l.strip().startswith("✗")]
                results[g].append({"run": i + 1, "verdict": verdict, "fails": fails[:6], "secs": round(time.time() - t0)})
                print(f"  run {i + 1}/{a.n} {g}: {verdict} ({round(time.time() - t0)}s)" + (f" {fails[0][:80]}" if fails else ""))
                ledger.record(ROOT / "games" / g, "coldstart", verdict=verdict, fails=fails[:6], run=i + 1, of=a.n, ref=head)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT, capture_output=True, text=True)
            shutil.rmtree(wt, ignore_errors=True)
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True, text=True)
    summary = {g: f"{sum(1 for r in rs if r['verdict'] == 'PASS')}/{len(rs)}" for g, rs in results.items()}
    out.write_text(json.dumps({"ref": head, "ts": ts, "n": a.n, "summary": summary, "runs": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    all_pass = True
    for g, s in summary.items():
        print(f"COLDSTART {g}: {s}"); all_pass &= s.split("/")[0] == s.split("/")[1]
    print(f"→ {out.relative_to(ROOT)}")
    print(f"COLDSTART: {'ALL_PASS' if all_pass else 'SOME_FAIL'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
