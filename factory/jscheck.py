#!/usr/bin/env python3
"""引擎 JS 语法自检（本机无 node）：用浏览器里的 acorn 解析 vendor/*.js，出错给行列。装配前必跑。"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parent.parent
def main(files):
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.set_content('<script src="https://cdnjs.cloudflare.com/ajax/libs/acorn/8.11.3/acorn.min.js"></script>'); pg.wait_for_function("() => window.acorn")
        for f in files:
            r = pg.evaluate("(src) => { try { acorn.parse(src, {ecmaVersion: 2022, sourceType: 'module'}); return 'OK' } catch(e) { return e.message + ' @' + JSON.stringify(e.loc) } }", Path(f).read_text(encoding="utf-8"))
            print(f"JS {f}: {r}"); bad += r != "OK"
        b.close()
    sys.exit(1 if bad else 0)
if __name__ == "__main__":
    main(sys.argv[1:] or [str(ROOT / "vendor/bf-runtime.js"), str(ROOT / "vendor/bf-lesson.js")])
