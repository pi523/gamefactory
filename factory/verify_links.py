#!/usr/bin/env python3
"""竞品链接核实：research.json 里每个 moon 的 url 必须真的打得开且页面标题含游戏名；不合格就用联网检索的**真实搜索结果 URL**（citations，不是模型编的）找替代，再核实。
用法: .venv/bin/python factory/verify_links.py games/<id> [--no-search]
产出: research.json 里每个 moon 多 link_status（verified|replaced|unverified）、link_title、link_checked_at；打印一张核实表。
"""
import argparse, html, json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402

STORES = ("apps.apple.com", "play.google.com", "taptap.cn", "taptap.com", "taptap.io", "store.steampowered.com", "mp.weixin.qq.com", "4399.com", "7k7k.com", "wandoujia.com")


def fetch_title(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(120000).decode("utf-8", "replace")
            t = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            og = re.search(r'property="og:title"\s+content="([^"]+)"', body, re.I)
            fetch_title.final_url = r.geturl()          # 跟随重定向后的真实地址（搜索引擎的 grounding 跳转链要落到商店页）
            return r.status, html.unescape((og.group(1) if og else (t.group(1) if t else ""))).strip()
    except Exception as e:
        fetch_title.final_url = url
        return None, f"ERR {str(e)[:60]}"


def name_tokens(name):
    toks = [w for w in re.split(r"[（）()：:/、·\s|\-—]+", name) if len(w) > 1]
    return toks or [name]


def title_matches(name, title):
    tl = (title or "").lower()
    return any(tok.lower() in tl for tok in name_tokens(name))


def find_candidates(name, platform=""):
    """联网检索，只取搜索结果里的真实 URL（citations）"""
    q = f"「{name}」{platform} 手机游戏 官方商店页面（App Store / Google Play / TapTap）链接。只需列出链接。"
    try:
        _, cites = llm.chat_web(q, role="web", max_results=6, max_tokens=800, tag="linkcheck")
    except Exception as e:
        print("   ✗ 检索失败:", str(e)[:80]); return []
    urls = [c["url"] for c in cites if any(s in c["url"] for s in STORES)] + [c["url"] for c in cites if not any(s in c["url"] for s in STORES)]
    seen = set(); out = []
    for u in urls:
        if u not in seen: seen.add(u); out.append(u)
    return out[:8]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("game_dir"); ap.add_argument("--no-search", action="store_true")
    a = ap.parse_args()
    game = Path(a.game_dir).resolve(); rp = game / "research.json"
    research = json.loads(rp.read_text(encoding="utf-8"))
    rows = []
    for m in research.get("moons", []):
        name = m.get("name", ""); url = m.get("url", "")
        status, title = fetch_title(url) if url else (None, "")
        ok = status == 200 and title_matches(name, title)
        if ok:
            final = getattr(fetch_title, "final_url", url)
            m.update({"url": final, "link_status": "verified", "link_title": title}); rows.append((name, "verified", final, title)); continue
        replaced = False
        if not a.no_search:
            for cand in find_candidates(name, m.get("platform", "")):
                s2, t2 = fetch_title(cand)
                if s2 == 200 and title_matches(name, t2):
                    final = getattr(fetch_title, "final_url", cand)
                    if "grounding-api-redirect" in final: continue        # 没落到真实页面的跳转链不采用
                    m.update({"url_original": url, "url": final, "link_status": "replaced", "link_title": t2}); rows.append((name, "replaced", final, t2)); replaced = True; break
        if not replaced:
            m.update({"link_status": "unverified", "link_title": title}); rows.append((name, "unverified", url, title))
        m["link_checked_at"] = time.strftime("%F %T")
    rp.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'竞品':24} {'状态':10} {'链接':60} 页面标题")
    for name, st, u, t in rows:
        print(f"{name[:22]:24} {st:10} {u[:58]:60} {(t or '')[:50]}")
    n_ok = sum(1 for r in rows if r[1] != "unverified")
    print(f"LINKS: {n_ok}/{len(rows)} 可信（verified+replaced），{len(rows)-n_ok} 条 unverified 不得作为月亮引用")


if __name__ == "__main__":
    main()
