#!/usr/bin/env python3
"""轮次台账：产线每跑一次判官（verify / realism / mutate / coldstart）都往 games/<id>/rounds.jsonl 追加一行，
带引擎与工厂关键文件的 sha256、git HEAD 与工作树是否脏。
目的：把"人手改引擎再续跑"的每一轮都记下来——不靠 reports/xxx-vNN.log 这类手工命名；latency.py 靠它算发现延迟与复发。
用法（库）: from ledger import record; record(game_dir, "verify", verdict="PASS", fails=[...], report="20260911-101602")
用法（命令）: .venv/bin/python factory/ledger.py games/<id>          # 打印最后几轮
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKED = ["vendor/bf-runtime.js", "vendor/bf-checks.js", "factory/generate.py", "factory/make_assets.py", "factory/verify.py", "factory/bot.py", "specs/rules/h5-hard-rules.json"]


def sha(p: Path):
    try: return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception: return None


def git_state():
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "factory", "vendor", "specs"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return head, [l[3:] for l in dirty.splitlines()][:20]
    except Exception:
        return None, []


def fingerprint(game: Path):
    fp = {k: sha(ROOT / k) for k in TRACKED}
    for f in ("game.js", "index.html", "lesson.json", "prd.json"):
        fp[f"game/{f}"] = sha(game / f)
    return fp


def record(game, kind, **data):
    game = Path(game).resolve()
    if not game.exists(): return None
    head, dirty = git_state()
    row = {"ts": time.strftime("%F %T"), "kind": kind, "git": head, "dirty": dirty, "fp": fingerprint(game)}
    row.update(data)
    (game / "rounds.jsonl").open("a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load(game):
    p = Path(game) / "rounds.jsonl"
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


if __name__ == "__main__":
    g = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if not g: sys.exit(__doc__)
    rows = load(g)
    print(f"{g.name}: {len(rows)} 轮（{g / 'rounds.jsonl'}）")
    for r in rows[-8:]:
        print(f"  {r['ts']} {r['kind']:8} {r.get('verdict', ''):5} git={r.get('git')}{'*' if r.get('dirty') else ''} engine={r['fp'].get('vendor/bf-lesson.js')} " + (str(r.get('fails', []))[:90] if r.get('fails') else ""))
