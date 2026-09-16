#!/usr/bin/env python3
"""由 PRD 的 assets 清单 + 写死的 style.json 生成生图任务单（还不调 API，先落盘让人/下游审）。
用法: python3 factory/imagegen_prompt.py games/sample-slice
输出: games/<id>/imagegen/jobs.json，每条含 prompt/negative/size/target 路径。
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    game = Path(sys.argv[1]).resolve()
    prd = json.loads((game / "prd.json").read_text(encoding="utf-8"))
    style = json.loads((ROOT / "specs/style.json").read_text(encoding="utf-8"))
    tpl = style["prompt_template"]; angles = tpl["angles"]
    jobs = []
    for a in prd["assets"]:
        for i in range(1, a["count"] + 1):
            angle = angles[(i - 1) % len(angles)]
            jobs.append({
                "target": f"assets/{a['category']}/{a['name']}{i}.png",
                "prompt": tpl["positive"].format(subject_en=a["subject_en"], subject_zh=a["name"], angle=angle),
                "negative": tpl["negative"],
                "size": style["output"]["size"], "format": "png-rgba",
                "style_id": style["id"], "postprocess": ["ensure_alpha", "check_assets"],
            })
    out = game / "imagegen"; out.mkdir(exist_ok=True)
    (out / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生图任务 {len(jobs)} 条 → {out.relative_to(ROOT)}/jobs.json")
    print("示例:", jobs[0]["prompt"][:120], "...")


if __name__ == "__main__":
    main()
